"""Main pipeline orchestrator: runs agents in sequence with fix loop."""

from __future__ import annotations

import logging
import re
import shutil
import time
from pathlib import Path
from typing import Optional

from agents.code_generator import CodeGeneratorAgent, _build_font_list
from agents.componentizer import ComponentizerAgent
from agents.fixer import FixerAgent
from agents.layout_strategy import LayoutStrategyAgent
from agents.position_generator import generate_deterministic_html_css
from agents.verification import VerificationAgent
from config import settings
from pipeline.job_manager import job_manager
from schemas.design_spec import DesignNode, DesignSpec
from schemas.diff_report import DiffReport
from schemas.job import JobResult, JobStatus, PluginVerificationResult

logger = logging.getLogger(__name__)


def _log_scores(job_id: str, report: DiffReport, label: str = "") -> None:
    """Compute and log plugin-facing scores from a DiffReport."""
    scores = PluginVerificationResult.from_diff_report(report)
    prefix = f"[job:{job_id}]"
    if label:
        prefix = f"{prefix} {label}"
    logger.info(
        "%s Scores: overall=%.1f, layout=%.1f, colors=%.1f, typography=%.1f, spacing=%.1f",
        prefix,
        scores.overall_score,
        scores.layout_score,
        scores.color_score,
        scores.typography_score,
        scores.spacing_score,
    )


def _build_design_context(spec: DesignSpec, section: str = "all") -> str:
    """Build a condensed design context string for the fixer agent.

    Args:
        spec: The design specification.
        section: Which metadata to include — "all", "typography", "spacing", or "assets".
    """
    root = spec.root
    lines: list[str] = []

    lines.append(f"- Frame dimensions: {root.bounds.width}px x {root.bounds.height}px")

    # Root background
    for fill in root.style.fills:
        if fill.visible and fill.type == "SOLID" and fill.color:
            lines.append(f"- Root background: background-color: {fill.color.to_css_rgba()}")
            break
        elif fill.visible and fill.type.startswith("GRADIENT_") and fill.gradient_stops:
            stops = ", ".join(
                f"{s.color.to_css_rgba() if s.color else '#000'} {s.position * 100:.0f}%"
                for s in fill.gradient_stops
            )
            if fill.type == "GRADIENT_LINEAR":
                angle = fill.gradient_angle_deg()
                angle_str = f"{angle}deg, " if angle is not None else ""
                lines.append(f"- Root background: background: linear-gradient({angle_str}{stops})")
            elif fill.type == "GRADIENT_RADIAL":
                lines.append(f"- Root background: background: radial-gradient({stops})")
            break

    # Root corner radius
    if root.style.corner_radius and root.style.corner_radius.to_css():
        lines.append(f"- Root border-radius: {root.style.corner_radius.to_css()}")

    # Fonts
    fonts = _build_font_list(spec)
    if fonts:
        lines.append(f"- Fonts used: {', '.join(fonts)}")

    # Top-level child positions (gives fixer concrete reference data)
    visible_children = [c for c in root.children if c.visible]
    if visible_children:
        lines.append("- Top-level child positions:")
        for child in visible_children[:20]:
            lines.append(
                f"  - \"{child.name}\" ({child.type}): "
                f"x={child.bounds.x}, y={child.bounds.y}, "
                f"w={child.bounds.width}, h={child.bounds.height}"
            )

    # Per-node typography metadata
    if section in ("all", "typography"):
        typo_lines = _collect_typography_metadata(root)
        if typo_lines:
            lines.append("\n## Typography Metadata (exact Figma values per text node)")
            lines.extend(typo_lines)

    # Per-node spacing metadata
    if section in ("all", "spacing"):
        spacing_lines = _collect_spacing_metadata(root)
        if spacing_lines:
            lines.append("\n## Spacing Metadata (exact Figma values per container)")
            lines.extend(spacing_lines)

    # Asset/image nodes
    if section in ("all", "assets"):
        asset_lines = _collect_asset_metadata(root, spec)
        if asset_lines:
            lines.append("\n## Asset Metadata (images, vectors, icons)")
            lines.extend(asset_lines)

    return "\n".join(lines)


def _collect_typography_metadata(root: DesignNode, max_nodes: int = 60) -> list[str]:
    """Walk the design tree and collect typography info for every TEXT node."""
    lines: list[str] = []
    stack = [root]
    count = 0
    while stack and count < max_nodes:
        node = stack.pop()
        if not node.visible:
            continue
        if node.type == "TEXT" and node.text and node.text.segments:
            count += 1
            segs = node.text.segments
            seg = segs[0]
            color_str = ""
            if seg.fill and seg.fill.color:
                color_str = seg.fill.color.to_css_rgba()
            lh = seg.line_height
            lh_str = f"{lh}px" if lh is not None else "auto"
            ls = seg.letter_spacing
            ls_str = f"{ls}px" if ls != 0 else "0"
            text_preview = (node.text.characters or "")[:40].replace("\n", " ")
            fs = seg.font_style if seg.font_style != "normal" else ""
            fs_str = f", font-style={fs}" if fs else ""
            lines.append(
                f"  - \"{node.name}\" (id={node.id}): "
                f"font-family=\"{seg.font_family}\", font-size={seg.font_size}px, "
                f"font-weight={seg.font_weight}{fs_str}, line-height={lh_str}, "
                f"letter-spacing={ls_str}, color={color_str}, "
                f"align={node.text.text_align_horizontal}, "
                f"text=\"{text_preview}\""
            )
            if len(segs) > 1:
                for i, s in enumerate(segs[1:4], 2):
                    s_color = s.fill.color.to_css_rgba() if s.fill and s.fill.color else ""
                    s_lh = f"{s.line_height}px" if s.line_height is not None else "auto"
                    s_fs = f", font-style={s.font_style}" if s.font_style != "normal" else ""
                    lines.append(
                        f"    segment {i}: font-size={s.font_size}px, "
                        f"font-weight={s.font_weight}{s_fs}, line-height={s_lh}, "
                        f"color={s_color}"
                    )
        stack.extend(reversed(node.children))
    return lines


def _collect_spacing_metadata(root: DesignNode, max_nodes: int = 60) -> list[str]:
    """Walk the design tree and collect spacing info for containers with auto-layout or padding."""
    lines: list[str] = []
    stack = [(root, None)]
    count = 0
    while stack and count < max_nodes:
        node, parent = stack.pop()
        if not node.visible:
            continue
        has_layout = node.layout.mode != "NONE"
        has_padding = any(
            v > 0 for v in (
                node.layout.padding_top, node.layout.padding_right,
                node.layout.padding_bottom, node.layout.padding_left,
            )
        )
        if (has_layout or has_padding) and node.children:
            count += 1
            parts = [f"  - \"{node.name}\" (id={node.id}):"]
            if has_layout:
                parts.append(f"layout={node.layout.mode}")
                if node.layout.item_spacing:
                    parts.append(f"gap={node.layout.item_spacing}px")
                parts.append(f"primary-align={node.layout.primary_axis_align}")
                parts.append(f"counter-align={node.layout.counter_axis_align}")
            if has_padding:
                parts.append(
                    f"padding={node.layout.padding_top}/{node.layout.padding_right}/"
                    f"{node.layout.padding_bottom}/{node.layout.padding_left}"
                )
            parts.append(
                f"bounds=({node.bounds.x}, {node.bounds.y}, "
                f"{node.bounds.width}x{node.bounds.height})"
            )
            lines.append(" ".join(parts))
        for child in reversed(node.children):
            stack.append((child, node))
    return lines


def _collect_asset_metadata(root: DesignNode, spec: DesignSpec, max_nodes: int = 40) -> list[str]:
    """Collect metadata for image/vector asset nodes."""
    asset_node_ids = {a.node_id for a in spec.assets}
    lines: list[str] = []
    stack = [root]
    count = 0
    while stack and count < max_nodes:
        node = stack.pop()
        if not node.visible:
            continue
        if node.id in asset_node_ids or node.type in ("VECTOR", "LINE", "STAR", "POLYGON"):
            count += 1
            lines.append(
                f"  - \"{node.name}\" (id={node.id}, type={node.type}): "
                f"bounds=({node.bounds.x}, {node.bounds.y}, "
                f"{node.bounds.width}x{node.bounds.height})"
            )
        stack.extend(reversed(node.children))
    return lines


async def run_pipeline(
    job_id: str,
    design_spec: DesignSpec,
    base_url: str = "",
    figma_screenshot: Optional[bytes] = None,
) -> None:
    """Execute the full Figma-to-HTML conversion pipeline.

    Pipeline stages:
    1. Validate design spec
    2. Layout strategy analysis
    3. HTML/CSS code generation
    4. Visual verification
    5. Fix loop (up to MAX_FIX_ITERATIONS)
    6. Componentization (optional optimization)

    Args:
        job_id: The job identifier.
        design_spec: The Figma design specification.
        base_url: Base URL for constructing download URLs.
        figma_screenshot: Pre-captured screenshot bytes from the plugin (PNG).
    """
    pipeline_start = time.monotonic()
    try:
        # Helper to set progress callbacks on agents
        def _setup_agent(agent):
            agent.set_progress_callback(job_manager.send_progress)
            return agent

        # === Stage 1: Validation ===
        await job_manager.update_status(
            job_id, JobStatus.PROCESSING,
            "Validating design specification",
            progress=5,
            step="Validating design specification",
        )

        root = design_spec.root
        if not root:
            raise ValueError("Design spec has no root node")

        total_nodes = 1 + len(root.get_all_descendants())
        frame_name = design_spec.metadata.frame_name or root.name
        logger.info("[job:%s] Pipeline started (frame=%s, nodes=%d)", job_id, frame_name, total_nodes)
        await job_manager.send_progress(
            job_id,
            f"Design spec validated: {total_nodes} nodes, "
            f"frame {root.bounds.width}x{root.bounds.height}px",
            {"total_nodes": total_nodes},
        )

        # === Stage 2: Layout Strategy ===
        await job_manager.update_status(
            job_id, JobStatus.PROCESSING,
            "Analyzing layout strategy",
            progress=20,
            step="Analyzing layout strategy",
        )

        stage_start = time.monotonic()
        layout_agent = _setup_agent(LayoutStrategyAgent(job_id))
        layout_plan = await layout_agent.execute(design_spec=design_spec)
        logger.info("[job:%s] LAYOUT completed in %.2fs (%d decisions)",
                     job_id, time.monotonic() - stage_start, len(layout_plan.decisions))

        # === Acquire Figma Screenshot (used for both code gen + verification) ===
        # 1. Use plugin-provided screenshot if available
        # 2. Fall back to Figma API if file_key is set
        # 3. Skip vision-based generation if neither is available
        if figma_screenshot:
            logger.info("[job:%s] Using plugin-provided frame screenshot (%d bytes)",
                        job_id, len(figma_screenshot))
            await job_manager.send_progress(
                job_id,
                f"Using plugin-provided screenshot ({len(figma_screenshot)} bytes)",
            )
        elif design_spec.metadata.file_key:
            try:
                from services.figma_api import get_frame_screenshot
                frame_id = design_spec.metadata.frame_id or root.id
                figma_screenshot = await get_frame_screenshot(
                    file_key=design_spec.metadata.file_key,
                    node_id=frame_id,
                    scale=2,
                )
            except Exception as e:
                logger.warning("Could not fetch Figma screenshot: %s", e)
                await job_manager.send_progress(
                    job_id,
                    f"Figma screenshot unavailable ({e}), will proceed without vision",
                )

        # === Stage 3: Code Generation ===
        await job_manager.update_status(
            job_id, JobStatus.PROCESSING,
            "Generating HTML and CSS",
            progress=35,
            step="Generating HTML and CSS",
        )

        stage_start = time.monotonic()
        allow_html_fixes = False

        if settings.USE_DETERMINISTIC_GENERATION:
            # ── Deterministic generation (no LLM) ──
            # Enable HTML fixes so the fixer can correct structural issues
            allow_html_fixes = True
            await job_manager.send_progress(
                job_id,
                "Using deterministic HTML/CSS generator",
            )

            # Build asset map (no filtering — include all assets as <img>)
            # Always use relative paths for deterministic generation
            asset_map: dict[str, str] = {}
            for asset in design_spec.assets:
                asset_map[asset.node_id] = f"assets/{asset.filename}"

            html_content, css_content = generate_deterministic_html_css(
                root=design_spec.root,
                asset_map=asset_map,
                layout_plan=layout_plan,
            )

            logger.info("[job:%s] DETERMINISTIC generation completed in %.2fs (html=%d, css=%d)",
                         job_id, time.monotonic() - stage_start, len(html_content), len(css_content))
        else:
            # ── GPT-4 fallback ──
            code_agent = _setup_agent(CodeGeneratorAgent(job_id))
            code_result = await code_agent.execute(
                design_spec=design_spec,
                layout_plan=layout_plan,
                base_url=base_url,
                figma_screenshot=figma_screenshot,
            )

            html_content = code_result["html"]
            css_content = code_result["css"]

            # Check completeness from code generation
            completeness = getattr(code_agent, "completeness", None)
            if completeness:
                logger.info(
                    "[job:%s] Code generation completeness: %.0f%% coverage, abbreviations=%s",
                    job_id, completeness.coverage_ratio * 100, completeness.has_abbreviation,
                )
                if completeness.coverage_ratio < 0.80 or completeness.has_abbreviation:
                    allow_html_fixes = True
                    logger.warning(
                        "[job:%s] Low coverage (%.0f%%) or abbreviations detected — enabling HTML fixes in fixer",
                        job_id, completeness.coverage_ratio * 100,
                    )
                    await job_manager.send_progress(
                        job_id,
                        f"Code coverage {completeness.coverage_ratio * 100:.0f}% — fixer will also fix HTML",
                    )

            logger.info("[job:%s] GENERATING completed in %.2fs (html=%d, css=%d)",
                         job_id, time.monotonic() - stage_start, len(html_content), len(css_content))

        # === Stage 4: Visual Verification ===
        await job_manager.update_status(
            job_id, JobStatus.VERIFYING,
            "Running visual verification",
            progress=55,
            step="Running visual verification",
        )

        verification_agent = _setup_agent(VerificationAgent(job_id))

        best_html = html_content
        best_css = css_content
        best_report: Optional[DiffReport] = None
        best_ssim = 0.0
        best_mismatch = 100.0
        iterations_used = 0

        best_typo_html = html_content
        best_typo_css = css_content
        best_typo_report: Optional[DiffReport] = None
        best_typo_score = 0.0

        stage_start = time.monotonic()
        if figma_screenshot:
            report = await verification_agent.execute(
                design_spec=design_spec,
                html_content=html_content,
                css_content=css_content,
                figma_screenshot=figma_screenshot,
            )

            best_report = report
            best_ssim = report.ssim_score
            best_mismatch = report.pixel_mismatch_percent

            init_scores = PluginVerificationResult.from_diff_report(report)
            best_typo_report = report
            best_typo_score = init_scores.typography_score
            best_typo_rendered: Optional[bytes] = None

            logger.info("[job:%s] VERIFICATION completed in %.2fs (SSIM=%.4f, mismatch=%.2f%%, passed=%s)",
                         job_id, time.monotonic() - stage_start, report.ssim_score,
                         report.pixel_mismatch_percent, report.passed)
            _log_scores(job_id, report, "Initial verification")

            rendered_screenshot_bytes: Optional[bytes] = None
            best_rendered_bytes: Optional[bytes] = None
            if report.rendered_screenshot_path:
                try:
                    rendered_screenshot_bytes = Path(report.rendered_screenshot_path).read_bytes()
                    best_rendered_bytes = rendered_screenshot_bytes
                    best_typo_rendered = rendered_screenshot_bytes
                except Exception as e:
                    logger.warning("[job:%s] Could not load rendered screenshot: %s", job_id, e)

            # Enable HTML fixes when pixel mismatch is severe
            if report.pixel_mismatch_percent > 20.0:
                allow_html_fixes = True
                logger.info(
                    "[job:%s] High pixel mismatch (%.1f%%) — enabling HTML fixes in fixer",
                    job_id, report.pixel_mismatch_percent,
                )

            # === Stage 5: Multi-phase fix loop ===
            if not report.passed:
                fixer_agent = _setup_agent(FixerAgent(job_id))
                current_css = css_content
                current_report = report

                fix_phases: list[tuple[str, int, str]] = [
                    ("general", settings.MAX_GENERAL_FIX_ITERATIONS, "all"),
                    ("typography", settings.MAX_SPECIALIZED_FIX_ITERATIONS + 1, "typography"),
                    ("spacing", settings.MAX_SPECIALIZED_FIX_ITERATIONS, "spacing"),
                    ("assets", settings.MAX_SPECIALIZED_FIX_ITERATIONS, "assets"),
                ]
                total_max_iters = sum(mi for _, mi, _ in fix_phases)
                global_iter = 0

                for phase_mode, phase_max, context_section in fix_phases:
                    if current_report.passed:
                        break

                    if phase_mode == "typography" and best_typo_report is not None:
                        cur_typo = PluginVerificationResult.from_diff_report(
                            current_report
                        ).typography_score
                        if best_typo_score > cur_typo:
                            logger.info(
                                "[job:%s] Switching to best-typography state for typography phase "
                                "(typo %.1f > current %.1f)",
                                job_id, best_typo_score, cur_typo,
                            )
                            current_css = best_typo_css
                            html_content = best_typo_html
                            current_report = best_typo_report
                            if best_typo_rendered is not None:
                                rendered_screenshot_bytes = best_typo_rendered

                    design_context = _build_design_context(design_spec, section=context_section)
                    consecutive_failures = 0

                    for phase_iter in range(1, phase_max + 1):
                        global_iter += 1
                        iterations_used = global_iter
                        fix_progress = 60 + int(30 * global_iter / total_max_iters)
                        phase_label = f"{phase_mode} fix {phase_iter}/{phase_max}"
                        await job_manager.update_status(
                            job_id, JobStatus.PROCESSING,
                            phase_label,
                            progress=fix_progress,
                            step=phase_label,
                        )

                        try:
                            fix_result = await fixer_agent.execute(
                                html_content=html_content,
                                css_content=current_css,
                                diff_report=current_report,
                                iteration=global_iter,
                                design_context=design_context,
                                allow_html_fixes=allow_html_fixes and phase_mode == "general",
                                figma_screenshot=figma_screenshot,
                                rendered_screenshot=rendered_screenshot_bytes,
                                mode=phase_mode,
                            )
                        except Exception as e:
                            logger.warning(
                                "[job:%s] %s fix iter %d failed (%s), keeping best CSS",
                                job_id, phase_mode, phase_iter, e,
                            )
                            await job_manager.send_progress(
                                job_id,
                                f"{phase_label} skipped (API error), continuing",
                            )
                            consecutive_failures += 1
                            if consecutive_failures >= 2:
                                break
                            continue

                        fixed_css = fix_result["css"]
                        fixed_html = fix_result.get("html")
                        verify_html = fixed_html if fixed_html else html_content

                        new_report = await verification_agent.execute(
                            design_spec=design_spec,
                            html_content=verify_html,
                            css_content=fixed_css,
                            figma_screenshot=figma_screenshot,
                        )

                        if new_report.rendered_screenshot_path:
                            try:
                                rendered_screenshot_bytes = Path(new_report.rendered_screenshot_path).read_bytes()
                            except Exception as e:
                                logger.warning("[job:%s] Could not load rendered screenshot: %s", job_id, e)

                        ssim_improved = new_report.ssim_score > current_report.ssim_score - 0.005
                        mismatch_improved = (
                            new_report.pixel_mismatch_percent <= current_report.pixel_mismatch_percent + 0.5
                        )
                        at_least_one_better = (
                            new_report.ssim_score > current_report.ssim_score
                            or new_report.pixel_mismatch_percent < current_report.pixel_mismatch_percent
                        )
                        improved = ssim_improved and mismatch_improved and at_least_one_better

                        iter_scores = PluginVerificationResult.from_diff_report(new_report)

                        if improved and phase_mode != "typography":
                            cur_scores = PluginVerificationResult.from_diff_report(current_report)
                            if iter_scores.typography_score < cur_scores.typography_score - 2.0:
                                logger.info(
                                    "[job:%s] %s iter %d: rejecting — typography would drop %.1f -> %.1f",
                                    job_id, phase_mode, phase_iter,
                                    cur_scores.typography_score, iter_scores.typography_score,
                                )
                                improved = False

                        logger.info("[job:%s] %s iter %d: improved=%s, SSIM=%.4f, mismatch=%.2f%%",
                                     job_id, phase_mode, phase_iter, improved,
                                     new_report.ssim_score, new_report.pixel_mismatch_percent)
                        _log_scores(job_id, new_report, f"{phase_mode} iter {phase_iter}")

                        if iter_scores.typography_score > best_typo_score:
                            best_typo_score = iter_scores.typography_score
                            best_typo_css = fixed_css
                            best_typo_html = fixed_html if fixed_html else html_content
                            best_typo_report = new_report
                            if rendered_screenshot_bytes is not None:
                                best_typo_rendered = rendered_screenshot_bytes

                        if improved:
                            consecutive_failures = 0
                            current_css = fixed_css
                            current_report = new_report
                            if fixed_html:
                                html_content = fixed_html

                            if (
                                new_report.ssim_score > best_ssim
                                or new_report.pixel_mismatch_percent < best_mismatch
                            ):
                                best_html = html_content
                                best_css = fixed_css
                                best_report = new_report
                                best_ssim = new_report.ssim_score
                                best_mismatch = new_report.pixel_mismatch_percent
                                if rendered_screenshot_bytes is not None:
                                    best_rendered_bytes = rendered_screenshot_bytes

                            await job_manager.send_progress(
                                job_id,
                                f"{phase_label} improved: SSIM {new_report.ssim_score:.4f}, "
                                f"mismatch {new_report.pixel_mismatch_percent:.2f}%",
                            )

                            if new_report.passed:
                                await job_manager.send_progress(
                                    job_id,
                                    f"Verification passed after {global_iter} total fix(es)!",
                                )
                                break
                        else:
                            consecutive_failures += 1
                            await job_manager.send_progress(
                                job_id,
                                f"{phase_label} did not improve, rolling back",
                            )
                            if best_rendered_bytes is not None:
                                rendered_screenshot_bytes = best_rendered_bytes
                            if consecutive_failures >= 2:
                                logger.info("[job:%s] Moving past %s phase after %d non-improvements",
                                            job_id, phase_mode, consecutive_failures)
                                break

                    # Sync current state with best before entering next phase
                    current_css = best_css
                    html_content = best_html
                    current_report = best_report or current_report
                    if best_rendered_bytes is not None:
                        rendered_screenshot_bytes = best_rendered_bytes

        else:
            await job_manager.send_progress(
                job_id,
                "Visual verification skipped (no reference screenshot).",
            )

        html_content = best_html
        css_content = best_css

        # === Stage 6: Componentization ===
        # Skip componentizer for deterministic output — it already produces clean CSS
        # and the componentizer can mangle property extraction across classes.
        if settings.USE_DETERMINISTIC_GENERATION:
            final_html = html_content
            final_css = css_content
            logger.info("[job:%s] Skipping componentization (deterministic mode)", job_id)
        else:
            await job_manager.update_status(
                job_id, JobStatus.PROCESSING,
                "Optimizing CSS",
                progress=92,
                step="Optimizing CSS",
            )

            stage_start = time.monotonic()
            componentizer = _setup_agent(ComponentizerAgent(job_id))
            comp_result = await componentizer.execute(
                html_content=html_content,
                css_content=css_content,
            )

            final_html = comp_result["html"]
            final_css = comp_result["css"]
            logger.info("[job:%s] COMPONENTIZATION completed in %.2fs", job_id, time.monotonic() - stage_start)

        # === Save Output ===
        output_dir = Path(settings.OUTPUT_DIR) / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        html_path = output_dir / "index.html"
        css_path = output_dir / "styles.css"

        # Build Google Fonts link from fonts used in the design
        fonts = _build_font_list(design_spec)
        if fonts:
            fonts_link = (
                f'<link rel="preconnect" href="https://fonts.googleapis.com">\n'
                f'    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
                f'    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
                + "&".join(
                    "family={fam}:ital,wght@{axes}".format(
                        fam=f.replace(" ", "+"),
                        axes=";".join(
                            "{ital},{w}".format(ital=ital, w=w)
                            for ital in (0, 1)
                            for w in (100, 200, 300, 400, 500, 600, 700, 800, 900)
                        ),
                    )
                    for f in fonts if f
                )
                + '&display=swap">'
            )
        else:
            fonts_link = ""

        # Build full HTML file with CSS link
        templates_dir = Path(__file__).parent.parent / "templates"
        base_template = (templates_dir / "base.html").read_text(encoding="utf-8")
        full_html = base_template.format(
            title=design_spec.metadata.frame_name or "Figma Design",
            fonts_link=fonts_link,
            content=final_html,
        )

        # Safety rewrite: normalize any remaining server-absolute asset paths
        # to relative paths so output works standalone (file://) and via API.
        full_html = full_html.replace(f"/jobs/{job_id}/assets/", "assets/")

        html_path.write_text(full_html, encoding="utf-8")

        # Prepend CSS reset
        css_reset = (templates_dir / "css_reset.css").read_text(encoding="utf-8")
        # Sanitize: strip any accidental "css" language tag artifact
        final_css = re.sub(r"^\s*css\s*\n", "", final_css)
        final_css = final_css.replace(f"/jobs/{job_id}/assets/", "assets/")
        full_css = css_reset + "\n\n" + final_css
        css_path.write_text(full_css, encoding="utf-8")

        # Copy assets from temp to output so they are co-located with HTML
        assets_src = Path(settings.TEMP_DIR) / job_id / "assets"
        assets_dst = output_dir / "assets"
        if assets_src.exists():
            try:
                if assets_dst.exists():
                    shutil.rmtree(assets_dst)
                shutil.copytree(assets_src, assets_dst)
                logger.info("[job:%s] Copied %d assets to output", job_id, len(list(assets_dst.iterdir())))
            except Exception as e:
                logger.error("[job:%s] Failed to copy assets from %s to %s: %s", job_id, assets_src, assets_dst, e)

        # Copy verification screenshots to output for easy access
        verification_dst = output_dir / "verification"
        verification_dst.mkdir(parents=True, exist_ok=True)
        temp_job_dir = Path(settings.TEMP_DIR) / job_id
        for screenshot_name in ("figma_screenshot.png", "rendered_screenshot.png", "diff_heatmap.png"):
            src = temp_job_dir / screenshot_name
            if src.exists():
                shutil.copy2(src, verification_dst / screenshot_name)
        logger.info("[job:%s] Copied verification screenshots to %s", job_id, verification_dst)

        # === Complete ===
        result = JobResult(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            html_content=final_html,
            css_content=final_css,
            verification=best_report,
            iterations_used=iterations_used,
            best_ssim=best_ssim,
            best_mismatch_percent=best_mismatch,
        )

        await job_manager.set_result(job_id, result, base_url=base_url)
        await job_manager.update_status(
            job_id, JobStatus.COMPLETED,
            "Conversion complete",
            progress=100,
            step="Conversion complete",
        )

        logger.info(
            "[job:%s] Pipeline complete in %.2fs: SSIM=%.4f, mismatch=%.2f%%, iterations=%d",
            job_id, time.monotonic() - pipeline_start, best_ssim, best_mismatch, iterations_used,
        )
        if best_report:
            _log_scores(job_id, best_report, "FINAL")

    except Exception as e:
        logger.exception("[job:%s] Pipeline failed after %.2fs: %s",
                          job_id, time.monotonic() - pipeline_start, e)
        await job_manager.set_error(job_id, str(e))
        await job_manager.update_status(
            job_id, JobStatus.FAILED, f"Pipeline error: {e}"
        )
