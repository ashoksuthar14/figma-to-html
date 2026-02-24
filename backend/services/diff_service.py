"""Image comparison service for visual verification."""

from __future__ import annotations

import io
import logging
import re
import time
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as ssim

from config import settings
from schemas.diff_report import DiffRegion, DiffReport, Severity

logger = logging.getLogger(__name__)

# Regex to parse px values from CSS (e.g. "12px", "3.5px")
_CSS_PX = re.compile(r"([\d.]+)\s*px")

# Grid size for region-based analysis
GRID_COLS = 8
GRID_ROWS = 8


def _load_image(data: bytes) -> np.ndarray:
    """Load image bytes into a numpy array (RGB).

    RGBA images (e.g. Figma frame screenshots with transparent background)
    are composited onto white before conversion so comparison matches
    rendered HTML with white background.
    """
    img = Image.open(io.BytesIO(data))
    if img.mode == "RGBA":
        white_bg = Image.new("RGB", img.size, (255, 255, 255))
        white_bg.paste(img, mask=img.split()[3])
        img = white_bg
    else:
        img = img.convert("RGB")
    return np.array(img)


def _downscale_for_comparison(img: np.ndarray, max_dim: int = 16000) -> np.ndarray:
    """Downscale an image so its largest dimension does not exceed max_dim.

    This prevents memory allocation errors during SSIM computation on
    high-resolution (e.g. 2x Retina) screenshots.  Both images in a pair
    must be downscaled by the same function so the comparison stays valid.
    Use max_dim=0 to skip downscaling entirely; default 16000 avoids aggressive
    downscaling of very tall pages (e.g. 1200x9944).
    """
    h, w = img.shape[:2]
    if max_dim <= 0 or (h <= max_dim and w <= max_dim):
        return img
    scale = max_dim / max(h, w)
    new_w = int(w * scale)
    new_h = int(h * scale)
    pil_img = Image.fromarray(img).resize((new_w, new_h), Image.LANCZOS)
    logger.debug("Downscaled image from %dx%d to %dx%d for comparison", w, h, new_w, new_h)
    return np.array(pil_img)


def _resize_to_match(img_a: np.ndarray, img_b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Align image dimensions by center-cropping to the smaller size (no scaling).

    Cropping preserves pixel alignment; scaling would distort positions and
    cause false layout mismatches.
    """
    h_a, w_a = img_a.shape[:2]
    h_b, w_b = img_b.shape[:2]

    if h_a == h_b and w_a == w_b:
        return img_a, img_b

    target_h = min(h_a, h_b)
    target_w = min(w_a, w_b)

    def _crop_center(arr: np.ndarray, th: int, tw: int) -> np.ndarray:
        h, w = arr.shape[:2]
        if h == th and w == tw:
            return arr
        top = (h - th) // 2
        left = (w - tw) // 2
        return arr[top : top + th, left : left + tw].copy()

    img_a = _crop_center(img_a, target_h, target_w)
    img_b = _crop_center(img_b, target_h, target_w)
    return img_a, img_b


def _pixel_diff(img_a: np.ndarray, img_b: np.ndarray, threshold: int = 64) -> np.ndarray:
    """Compute per-pixel difference mask.

    Args:
        img_a: First image array (H, W, 3).
        img_b: Second image array (H, W, 3).
        threshold: Per-channel difference threshold to count as mismatch (64 allows font anti-aliasing differences).

    Returns:
        Boolean mask (H, W) where True = pixel mismatch.
    """
    diff = np.abs(img_a.astype(np.int16) - img_b.astype(np.int16))
    # A pixel is mismatched if any channel differs by more than threshold
    mismatch = np.any(diff > threshold, axis=2)
    return mismatch


def _compute_ssim(img_a: np.ndarray, img_b: np.ndarray) -> float:
    """Compute structural similarity index between two images."""
    # SSIM needs at least 7x7 window; handle tiny images
    min_dim = min(img_a.shape[0], img_a.shape[1])
    win_size = min(7, min_dim)
    if win_size % 2 == 0:
        win_size -= 1
    if win_size < 3:
        # Images too small for SSIM, fall back to pixel comparison
        return 1.0 if np.array_equal(img_a, img_b) else 0.0

    score, _ = ssim(
        img_a, img_b,
        win_size=win_size,
        channel_axis=2,
        full=True,
    )
    return float(score)


def _generate_diff_heatmap(
    img_a: np.ndarray,
    img_b: np.ndarray,
    mismatch_mask: np.ndarray,
) -> bytes:
    """Generate a visual diff heatmap image.

    Blends the two images and overlays red on mismatched areas.
    """
    h, w = img_a.shape[:2]

    # Create a blended base image
    blended = ((img_a.astype(np.float32) + img_b.astype(np.float32)) / 2).astype(np.uint8)

    # Create the heatmap overlay
    heatmap = blended.copy()
    # Highlight mismatched pixels in red
    heatmap[mismatch_mask, 0] = 255  # Red channel
    heatmap[mismatch_mask, 1] = 0    # Green channel
    heatmap[mismatch_mask, 2] = 0    # Blue channel

    # Alpha blend: 60% heatmap, 40% original blend for context
    result = (0.6 * heatmap.astype(np.float32) + 0.4 * blended.astype(np.float32)).astype(np.uint8)

    # Convert to PNG bytes
    img = Image.fromarray(result)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _simple_edge_magnitude(gray: np.ndarray) -> np.ndarray:
    """Compute edge magnitude using simple Sobel-like 3x3 kernels (NumPy only)."""
    # Pad to handle borders
    padded = np.pad(gray, 1, mode="edge")
    # Horizontal gradient (Sobel-x approximation)
    gx = (
        -padded[:-2, :-2] + padded[:-2, 2:]
        - 2 * padded[1:-1, :-2] + 2 * padded[1:-1, 2:]
        - padded[2:, :-2] + padded[2:, 2:]
    )
    # Vertical gradient (Sobel-y approximation)
    gy = (
        -padded[:-2, :-2] - 2 * padded[:-2, 1:-1] - padded[:-2, 2:]
        + padded[2:, :-2] + 2 * padded[2:, 1:-1] + padded[2:, 2:]
    )
    return np.sqrt(gx ** 2 + gy ** 2)


def _classify_mismatch(
    cell_a: np.ndarray,
    cell_b: np.ndarray,
) -> str:
    """Classify the type of mismatch between two image cells.

    Uses edge detection alongside gray/color difference to distinguish
    layout issues from font rendering and color differences.

    Args:
        cell_a: Region from image A (H, W, 3).
        cell_b: Region from image B (H, W, 3).

    Returns:
        A descriptive string containing classifying keywords.
    """
    diff = np.abs(cell_a.astype(np.int16) - cell_b.astype(np.int16))

    # Convert to grayscale for structural analysis
    gray_a = np.mean(cell_a, axis=2).astype(np.float64)
    gray_b = np.mean(cell_b, axis=2).astype(np.float64)
    gray_diff = float(np.mean(np.abs(gray_a - gray_b)))

    # Edge-based structural difference
    edges_a = _simple_edge_magnitude(gray_a)
    edges_b = _simple_edge_magnitude(gray_b)
    edge_diff = float(np.mean(np.abs(edges_a - edges_b)))

    # Colour-only difference (remove luminance component)
    mean_diff = float(np.mean(diff))
    color_diff = mean_diff - gray_diff

    # Layout: both edge structure AND gray values differ significantly
    if edge_diff > 20 and gray_diff > 80:
        return "Layout/structural position mismatch"
    if color_diff > 30:
        return "Color/background fill mismatch"
    if gray_diff > 40:
        return "Typography/font text mismatch"
    return "Spacing/alignment gap mismatch"


def _analyze_regions(
    mismatch_mask: np.ndarray,
    img_a: np.ndarray | None = None,
    img_b: np.ndarray | None = None,
    grid_rows: int = GRID_ROWS,
    grid_cols: int = GRID_COLS,
) -> list[DiffRegion]:
    """Divide the image into a grid and identify mismatch regions.

    Args:
        mismatch_mask: Boolean mask (H, W) of mismatched pixels.
        img_a: First image array (optional, enables classification).
        img_b: Second image array (optional, enables classification).
        grid_rows: Number of grid rows.
        grid_cols: Number of grid columns.

    Returns:
        List of DiffRegion objects for cells with significant mismatches.
    """
    h, w = mismatch_mask.shape
    cell_h = h // grid_rows
    cell_w = w // grid_cols
    regions: list[DiffRegion] = []
    can_classify = img_a is not None and img_b is not None

    if cell_h == 0 or cell_w == 0:
        return regions

    for row in range(grid_rows):
        for col in range(grid_cols):
            y_start = row * cell_h
            y_end = (row + 1) * cell_h if row < grid_rows - 1 else h
            x_start = col * cell_w
            x_end = (col + 1) * cell_w if col < grid_cols - 1 else w

            cell = mismatch_mask[y_start:y_end, x_start:x_end]
            cell_total = cell.size
            cell_mismatched = int(np.sum(cell))

            if cell_total == 0:
                continue

            cell_pct = (cell_mismatched / cell_total) * 100

            # Skip regions with negligible mismatch
            if cell_pct < 0.1:
                continue

            # Determine severity
            if cell_pct >= 10.0:
                severity = Severity.HIGH
            elif cell_pct >= 3.0:
                severity = Severity.MEDIUM
            else:
                severity = Severity.LOW

            # Classify the type of mismatch when images are available
            if can_classify:
                classification = _classify_mismatch(
                    img_a[y_start:y_end, x_start:x_end],
                    img_b[y_start:y_end, x_start:x_end],
                )
                issue = f"{classification} ({cell_pct:.1f}% of region)"
            else:
                sev_label = {Severity.HIGH: "Major", Severity.MEDIUM: "Moderate", Severity.LOW: "Minor"}
                issue = f"{sev_label[severity]} mismatch ({cell_pct:.1f}% of region)"

            regions.append(DiffRegion(
                x=float(x_start),
                y=float(y_start),
                width=float(x_end - x_start),
                height=float(y_end - y_start),
                area=float(cell_mismatched),
                issue=issue,
                severity=severity,
                mismatch_percent=cell_pct,
            ))

    # Sort by severity (high first) then by mismatch percentage
    severity_order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
    regions.sort(key=lambda r: (severity_order[r.severity], -r.mismatch_percent))

    return regions


def _parse_css_absolute_boxes(css_content: str) -> list[tuple[str, float, float, float, float]]:
    """Parse CSS and return (selector, left, top, width, height) for each rule with dimensions.

    Extracts left, top, width, height in px. Defaults left/top to 0 if missing.
    Only includes rules that have at least width and height.
    """
    cleaned = re.sub(r"/\*.*?\*/", "", css_content, flags=re.DOTALL)
    results: list[tuple[str, float, float, float, float]] = []
    pos = 0
    while pos < len(cleaned):
        while pos < len(cleaned) and cleaned[pos] in " \t\n\r":
            pos += 1
        if pos >= len(cleaned):
            break
        brace_start = cleaned.find("{", pos)
        if brace_start == -1:
            break
        selector = cleaned[pos:brace_start].strip()
        depth = 1
        i = brace_start + 1
        while i < len(cleaned) and depth > 0:
            if cleaned[i] == "{":
                depth += 1
            elif cleaned[i] == "}":
                depth -= 1
            i += 1
        block = cleaned[brace_start + 1 : i - 1]
        pos = i

        def _get_px(prop: str) -> Optional[float]:
            m = re.search(rf"{re.escape(prop)}\s*:\s*([\d.]+)\s*px", block, re.I)
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    pass
            return None

        left = _get_px("left")
        top = _get_px("top")
        width = _get_px("width")
        height = _get_px("height")
        if width is None or height is None:
            continue
        left = left if left is not None else 0.0
        top = top if top is not None else 0.0
        results.append((selector, left, top, width, height))

    return results


def get_region_suspect_selectors(
    css_content: str,
    regions: list[DiffRegion],
) -> list[list[str]]:
    """Map each diff region to CSS selectors whose bounding box intersects the region.

    Returns a list of the same length as regions; each element is a list of
    selector strings that overlap that region's bounding box.
    """
    boxes = _parse_css_absolute_boxes(css_content)
    out: list[list[str]] = []
    for r in regions:
        r_left = r.x
        r_top = r.y
        r_right = r.x + r.width
        r_bottom = r.y + r.height
        suspects: list[str] = []
        for sel, left, top, w, h in boxes:
            s_right = left + w
            s_bottom = top + h
            if not (r_left > s_right or r_right < left or r_top > s_bottom or r_bottom < top):
                suspects.append(sel)
        out.append(suspects)
    return out


async def compare_images(
    image_a: bytes,
    image_b: bytes,
    save_diff: bool = True,
    job_id: Optional[str] = None,
) -> DiffReport:
    """Compare two images and generate a comprehensive diff report.

    Args:
        image_a: First image (expected / Figma screenshot) as PNG bytes.
        image_b: Second image (actual / rendered HTML) as PNG bytes.
        save_diff: Whether to save the diff heatmap to disk.
        job_id: Job ID for file naming.

    Returns:
        DiffReport with comparison results.
    """
    compare_start = time.monotonic()
    arr_a = _load_image(image_a)
    arr_b = _load_image(image_b)

    # Ensure same dimensions
    orig_a_shape = arr_a.shape[:2]
    orig_b_shape = arr_b.shape[:2]
    arr_a, arr_b = _resize_to_match(arr_a, arr_b)
    if orig_a_shape != arr_b.shape[:2] or orig_b_shape != arr_a.shape[:2]:
        logger.info("Resized images to match: %s & %s -> %s",
                     orig_a_shape, orig_b_shape, arr_a.shape[:2])

    h, w = arr_a.shape[:2]
    total_pixels = h * w

    # Pixel-level comparison at full resolution
    mismatch_mask = _pixel_diff(arr_a, arr_b)
    mismatched_pixels = int(np.sum(mismatch_mask))
    mismatch_percent = (mismatched_pixels / total_pixels) * 100 if total_pixels > 0 else 0.0

    # SSIM on downscaled copies to reduce sensitivity to anti-aliasing differences
    SSIM_MAX_DIM = 2000
    arr_a_ssim = _downscale_for_comparison(arr_a, max_dim=SSIM_MAX_DIM)
    arr_b_ssim = _downscale_for_comparison(arr_b, max_dim=SSIM_MAX_DIM)
    ssim_score = _compute_ssim(arr_a_ssim, arr_b_ssim)

    # Dynamic grid rows: scale based on image aspect ratio for tall designs
    aspect_ratio = h / max(w, 1)
    dynamic_rows = GRID_ROWS
    if aspect_ratio > 2.0:
        dynamic_rows = min(int(GRID_ROWS * aspect_ratio / 1.0), 32)

    # Region analysis (pass images for mismatch classification)
    regions = _analyze_regions(
        mismatch_mask, img_a=arr_a, img_b=arr_b, grid_rows=dynamic_rows,
    )

    # Generate and optionally save diff heatmap
    diff_image_path: Optional[str] = None
    if save_diff and mismatched_pixels > 0:
        heatmap_bytes = _generate_diff_heatmap(arr_a, arr_b, mismatch_mask)
        if job_id:
            diff_dir = Path(settings.TEMP_DIR) / job_id
            diff_dir.mkdir(parents=True, exist_ok=True)
            diff_path = diff_dir / "diff_heatmap.png"
            diff_path.write_bytes(heatmap_bytes)
            diff_image_path = str(diff_path)

    # Determine pass/fail
    passed = (
        mismatch_percent <= settings.PIXEL_MISMATCH_THRESHOLD
        and ssim_score >= settings.SSIM_THRESHOLD
    )

    report = DiffReport(
        passed=passed,
        pixel_mismatch_percent=round(mismatch_percent, 4),
        ssim_score=round(ssim_score, 6),
        diff_image_path=diff_image_path,
        regions=regions,
        total_pixels=total_pixels,
        mismatched_pixels=mismatched_pixels,
    )

    logger.info(
        "Image comparison complete: %s (mismatch=%.2f%%, SSIM=%.4f, regions=%d) in %.2fs",
        "PASS" if passed else "FAIL",
        mismatch_percent,
        ssim_score,
        len(regions),
        time.monotonic() - compare_start,
    )

    return report
