"""Playwright-based headless browser service for rendering HTML to screenshots.

Uses the sync Playwright API running in a thread pool to avoid Windows
event loop limitations (SelectorEventLoop doesn't support subprocesses).
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Browser, Page

logger = logging.getLogger(__name__)

_browser: Optional[Browser] = None
_pw_context = None
_lock = threading.Lock()


def _ensure_browser() -> Browser:
    """Ensure a global Chromium browser instance is running (sync, thread-safe)."""
    global _browser, _pw_context
    with _lock:
        if _browser is None or not _browser.is_connected():
            _pw_context = sync_playwright().start()
            _browser = _pw_context.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--font-render-hinting=none",
                ],
            )
            logger.info("Chromium browser launched")
    return _browser


async def close_browser() -> None:
    """Close the global browser instance if open."""
    global _browser, _pw_context

    def _close():
        global _browser, _pw_context
        with _lock:
            if _browser and _browser.is_connected():
                _browser.close()
                _browser = None
            if _pw_context:
                _pw_context.stop()
                _pw_context = None
            logger.info("Chromium browser closed")

    await asyncio.to_thread(_close)


def build_full_html(
    html_content: str,
    css_content: str,
    fonts: list[str] | None = None,
) -> str:
    """Combine HTML and CSS into a full page document.

    Args:
        html_content: HTML body content.
        css_content: CSS stylesheet content.
        fonts: Optional list of font family names to load from Google Fonts.
    """
    # Use same CSS reset as output HTML so Playwright verification matches
    _templates_dir = Path(__file__).resolve().parent.parent / "templates"
    _css_reset = (_templates_dir / "css_reset.css").read_text(encoding="utf-8")

    # Build Google Fonts link tags if fonts are provided
    _VARIABLE_WIDTH_FONTS: dict[str, str] = {
        "League Gothic": "family=League+Gothic:wdth,wght@75..100,400",
    }

    fonts_link = ""
    if fonts:
        family_params: list[str] = []
        for f in fonts:
            if not f:
                continue
            if f in _VARIABLE_WIDTH_FONTS:
                family_params.append(_VARIABLE_WIDTH_FONTS[f])
            else:
                axes = ";".join(
                    f"{ital},{w}"
                    for ital in (0, 1)
                    for w in (100, 200, 300, 400, 500, 600, 700, 800, 900)
                )
                family_params.append(
                    f"family={f.replace(' ', '+')}:ital,wght@{axes}"
                )
        fonts_link = (
            '    <link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            '    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
            + "&".join(family_params)
            + '&display=swap">\n'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
{fonts_link}    <style>
{_css_reset}
    </style>
    <style>
{css_content}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""


def _render_sync(
    html_content: str,
    css_content: str,
    width: int,
    height: int,
    scale: float = 2.0,
) -> bytes:
    """Render HTML+CSS to a PNG screenshot synchronously (runs in thread pool)."""
    render_start = time.monotonic()
    full_html = build_full_html(html_content, css_content)

    browser = _ensure_browser()
    context = browser.new_context(
        viewport={"width": width, "height": height},
        device_scale_factor=scale,
    )
    page = context.new_page()

    try:
        page.set_content(full_html, wait_until="networkidle")

        # Wait for any web fonts to load
        try:
            page.evaluate("() => document.fonts.ready")
        except Exception:
            logger.info("Font loading check skipped (not supported or timed out)")

        # Small additional wait for any rendering to settle
        import time as _time
        _time.sleep(1.0)

        screenshot_bytes = page.screenshot(
            type="png",
            full_page=False,
            animations="disabled",
        )

        logger.info(
            "Rendered HTML screenshot (viewport): %dx%d @%.1fx (%d bytes) in %.2fs",
            width, height, scale, len(screenshot_bytes), time.monotonic() - render_start,
        )
        return screenshot_bytes
    finally:
        page.close()
        context.close()


async def render_html_to_screenshot(
    html_content: str,
    css_content: str,
    width: int,
    height: int,
    scale: float = 2.0,
    wait_timeout: int = 5000,
) -> bytes:
    """Render HTML+CSS to a PNG screenshot using headless Chromium.

    Args:
        html_content: The HTML body content.
        css_content: The CSS stylesheet content.
        width: Viewport width in CSS pixels.
        height: Viewport height in CSS pixels.
        scale: Device scale factor for retina rendering.
        wait_timeout: Max ms to wait for fonts/images to load.

    Returns:
        PNG image bytes.
    """
    return await asyncio.to_thread(
        _render_sync, html_content, css_content, width, height, scale,
    )


def _render_file_sync(
    html_path: str,
    width: int,
    height: int,
    scale: float = 2.0,
    full_page: bool = False,
) -> bytes:
    """Render an HTML file to a PNG screenshot synchronously."""
    browser = _ensure_browser()
    context = browser.new_context(
        viewport={"width": width, "height": height},
        device_scale_factor=scale,
    )
    page = context.new_page()

    try:
        file_url = Path(html_path).resolve().as_uri()
        page.goto(file_url, wait_until="networkidle")

        try:
            page.evaluate("() => document.fonts.ready")
        except Exception:
            pass

        import time as _time
        _time.sleep(1.0)

        return page.screenshot(
            type="png",
            full_page=full_page,
            animations="disabled",
        )
    finally:
        page.close()
        context.close()


async def render_html_file_to_screenshot(
    html_path: str,
    width: int,
    height: int,
    scale: float = 2.0,
    full_page: bool = False,
) -> bytes:
    """Render an HTML file to a PNG screenshot.

    Args:
        html_path: Path to the HTML file on disk.
        width: Viewport width.
        height: Viewport height.
        scale: Device scale factor.
        full_page: If True, capture the entire page. If False, capture only the viewport.

    Returns:
        PNG image bytes.
    """
    return await asyncio.to_thread(
        _render_file_sync, html_path, width, height, scale, full_page,
    )
