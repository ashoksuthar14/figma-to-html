"""Agent 4 - Visual Verification: Compares Figma design to rendered HTML output."""

from __future__ import annotations

import io
import logging
import time
from pathlib import Path
from typing import Optional

from PIL import Image

from agents.base import BaseAgent
from schemas.design_spec import DesignSpec
from schemas.diff_report import DiffReport
from services import browser_service, diff_service
from services.figma_api import get_frame_screenshot

logger = logging.getLogger(__name__)


class VerificationAgent(BaseAgent):
    """Compares the Figma design screenshot against the rendered HTML output."""

    async def execute(
        self,
        design_spec: DesignSpec,
        html_content: str,
        css_content: str,
        figma_screenshot: Optional[bytes] = None,
    ) -> DiffReport:
        """Run visual verification between Figma design and generated code.

        Args:
            design_spec: The original design spec (for dimensions and file info).
            html_content: Generated HTML body content.
            css_content: Generated CSS stylesheet.
            figma_screenshot: Pre-fetched Figma screenshot bytes (optional).

        Returns:
            DiffReport with comparison results.
        """
        agent_start = time.monotonic()
        logger.info("[job:%s] Verification started", self.job_id)
        root = design_spec.root
        width = max(1, int(root.bounds.width))
        height = max(1, int(root.bounds.height))

        # Step 1: Get Figma screenshot
        if figma_screenshot is None:
            await self.report_progress("Fetching Figma frame screenshot")
            try:
                file_key = design_spec.metadata.file_key
                frame_id = design_spec.metadata.frame_id or root.id
                figma_screenshot = await get_frame_screenshot(
                    file_key=file_key,
                    node_id=frame_id,
                    scale=2,
                    fmt="png",
                )
            except Exception as e:
                logger.error("Failed to fetch Figma screenshot: %s", e)
                await self.report_progress(
                    f"Figma screenshot fetch failed: {e}. "
                    "Skipping visual verification."
                )
                return DiffReport(
                    passed=False,
                    pixel_mismatch_percent=100.0,
                    ssim_score=0.0,
                    regions=[],
                )

        logger.info("[job:%s] Figma screenshot: %d bytes", self.job_id, len(figma_screenshot))
        # Save Figma screenshot for reference
        from config import settings
        temp_dir = Path(settings.TEMP_DIR) / self.job_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        figma_path = temp_dir / "figma_screenshot.png"
        figma_path.write_bytes(figma_screenshot)
        try:
            figma_img = Image.open(io.BytesIO(figma_screenshot))
            logger.info("[job:%s] Figma screenshot dimensions: %dx%d", self.job_id, figma_img.width, figma_img.height)

            render_scale = 2
            expected_w = width * render_scale
            expected_h = height * render_scale

            if figma_img.width > int(expected_w * 1.2) or figma_img.height > int(expected_h * 1.2):
                orig_w, orig_h = figma_img.width, figma_img.height
                crop_w = min(expected_w, figma_img.width)
                crop_h = min(expected_h, figma_img.height)
                left = 0
                top = 0
                figma_img = figma_img.crop((left, top, left + crop_w, top + crop_h))
                buf = io.BytesIO()
                figma_img.save(buf, format="PNG")
                figma_screenshot = buf.getvalue()
                figma_path.write_bytes(figma_screenshot)
                logger.info(
                    "[job:%s] Pre-cropped Figma screenshot from %dx%d to %dx%d (expected %dx%d)",
                    self.job_id, orig_w, orig_h, figma_img.width, figma_img.height,
                    expected_w, expected_h,
                )
        except Exception:
            pass

        # Step 2: Render generated HTML to screenshot
        # Save HTML as a file so images with relative paths resolve correctly.
        # page.set_content() renders at about:blank where asset URLs can't load;
        # page.goto(file://...) resolves ./assets/... paths relative to the file.
        await self.report_progress("Rendering generated HTML to screenshot")
        try:
            # Rewrite asset URLs to relative paths for file:// rendering.
            # Handle both legacy format (/jobs/{id}/assets/) and deterministic (assets/).
            local_html = html_content.replace(
                f"/jobs/{self.job_id}/assets/", "./assets/",
            )
            local_css = css_content.replace(
                f"/jobs/{self.job_id}/assets/", "./assets/",
            )
            # Deterministic generator uses bare "assets/" — make it "./assets/"
            # (only replace when not already prefixed with ./ or /)
            import re as _re
            local_html = _re.sub(r'(?<![./])assets/', './assets/', local_html)
            local_css = _re.sub(r'(?<![./])assets/', './assets/', local_css)

            # Include Google Fonts in verification renderer for accurate font rendering
            from agents.code_generator import _build_font_list
            fonts = _build_font_list(design_spec)

            full_html = browser_service.build_full_html(local_html, local_css, fonts=fonts)
            verify_path = temp_dir / "verify.html"
            verify_path.write_text(full_html, encoding="utf-8")

            rendered_screenshot = await browser_service.render_html_file_to_screenshot(
                html_path=str(verify_path),
                width=width,
                height=height,
                scale=2,
                full_page=False,
            )
        except Exception as e:
            logger.error("Failed to render HTML screenshot: %s", e)
            await self.report_progress(f"HTML rendering failed: {e}")
            return DiffReport(
                passed=False,
                pixel_mismatch_percent=100.0,
                ssim_score=0.0,
                regions=[],
            )

        logger.info("[job:%s] Rendered screenshot: %d bytes", self.job_id, len(rendered_screenshot))
        try:
            rendered_img = Image.open(io.BytesIO(rendered_screenshot))
            logger.info("[job:%s] Rendered screenshot dimensions: %dx%d", self.job_id, rendered_img.width, rendered_img.height)
        except Exception:
            pass
        # Save rendered screenshot for reference
        rendered_path = temp_dir / "rendered_screenshot.png"
        rendered_path.write_bytes(rendered_screenshot)

        # Step 3: Compare screenshots
        await self.report_progress("Comparing Figma vs rendered screenshots")
        report = await diff_service.compare_images(
            image_a=figma_screenshot,
            image_b=rendered_screenshot,
            save_diff=True,
            job_id=self.job_id,
        )

        report.figma_screenshot_path = str(figma_path)
        report.rendered_screenshot_path = str(rendered_path)

        logger.info("[job:%s] Verification: passed=%s, SSIM=%.4f, mismatch=%.2f%% (%.2fs)",
                     self.job_id, report.passed, report.ssim_score,
                     report.pixel_mismatch_percent, time.monotonic() - agent_start)
        await self.report_progress(
            report.summary,
            {
                "passed": report.passed,
                "mismatch_percent": report.pixel_mismatch_percent,
                "ssim_score": report.ssim_score,
                "regions_count": len(report.regions),
            },
        )

        return report
