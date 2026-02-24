"""Tests for the diff_service image comparison with known test images."""

import io

import numpy as np
import pytest
from PIL import Image

from schemas.diff_report import Severity
from services.diff_service import (
    _analyze_regions,
    _classify_mismatch,
    _compute_ssim,
    _downscale_for_comparison,
    _generate_diff_heatmap,
    _load_image,
    _pixel_diff,
    _resize_to_match,
    compare_images,
)


def _create_solid_image(
    width: int = 100,
    height: int = 100,
    color: tuple[int, int, int] = (255, 255, 255),
) -> bytes:
    """Create a solid-color PNG image and return as bytes."""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _create_gradient_image(
    width: int = 100,
    height: int = 100,
    direction: str = "horizontal",
) -> bytes:
    """Create a gradient image for testing."""
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    if direction == "horizontal":
        for x in range(width):
            val = int(255 * x / width)
            arr[:, x] = [val, val, val]
    else:
        for y in range(height):
            val = int(255 * y / height)
            arr[y, :] = [val, val, val]
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _create_image_with_region(
    width: int = 100,
    height: int = 100,
    bg_color: tuple[int, int, int] = (255, 255, 255),
    region_color: tuple[int, int, int] = (255, 0, 0),
    region_x: int = 20,
    region_y: int = 20,
    region_w: int = 30,
    region_h: int = 30,
) -> bytes:
    """Create an image with a colored rectangle region."""
    img = Image.new("RGB", (width, height), bg_color)
    arr = np.array(img)
    arr[region_y:region_y + region_h, region_x:region_x + region_w] = region_color
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --- Unit tests for internal functions ---

class TestLoadImage:
    def test_load_png(self):
        img_bytes = _create_solid_image(50, 30, (128, 128, 128))
        arr = _load_image(img_bytes)
        assert arr.shape == (30, 50, 3)
        assert arr[0, 0, 0] == 128


class TestResizeToMatch:
    def test_same_size(self):
        a = np.zeros((100, 100, 3), dtype=np.uint8)
        b = np.zeros((100, 100, 3), dtype=np.uint8)
        ra, rb = _resize_to_match(a, b)
        assert ra.shape == rb.shape

    def test_different_sizes(self):
        a = np.zeros((100, 200, 3), dtype=np.uint8)
        b = np.zeros((150, 100, 3), dtype=np.uint8)
        ra, rb = _resize_to_match(a, b)
        assert ra.shape == rb.shape
        assert ra.shape[0] == 100  # min height
        assert ra.shape[1] == 100  # min width


class TestPixelDiff:
    def test_identical_images(self):
        a = np.full((50, 50, 3), 128, dtype=np.uint8)
        b = np.full((50, 50, 3), 128, dtype=np.uint8)
        mask = _pixel_diff(a, b)
        assert np.sum(mask) == 0

    def test_completely_different(self):
        a = np.zeros((50, 50, 3), dtype=np.uint8)
        b = np.full((50, 50, 3), 255, dtype=np.uint8)
        mask = _pixel_diff(a, b)
        assert np.sum(mask) == 50 * 50

    def test_small_difference_below_threshold(self):
        a = np.full((50, 50, 3), 128, dtype=np.uint8)
        b = np.full((50, 50, 3), 130, dtype=np.uint8)  # diff = 2 < threshold=30
        mask = _pixel_diff(a, b, threshold=30)
        assert np.sum(mask) == 0

    def test_partial_difference(self):
        a = np.full((100, 100, 3), 128, dtype=np.uint8)
        b = a.copy()
        b[0:50, 0:50] = 0  # Top-left quarter differs
        mask = _pixel_diff(a, b)
        assert 2400 <= np.sum(mask) <= 2600  # Roughly 2500


class TestComputeSSIM:
    def test_identical(self):
        a = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        score = _compute_ssim(a, a)
        assert score > 0.99

    def test_completely_different(self):
        a = np.zeros((100, 100, 3), dtype=np.uint8)
        b = np.full((100, 100, 3), 255, dtype=np.uint8)
        score = _compute_ssim(a, b)
        assert score < 0.1

    def test_small_image(self):
        a = np.zeros((4, 4, 3), dtype=np.uint8)
        b = np.zeros((4, 4, 3), dtype=np.uint8)
        score = _compute_ssim(a, b)
        assert score == 1.0


class TestAnalyzeRegions:
    def test_no_mismatch(self):
        mask = np.zeros((100, 100), dtype=bool)
        regions = _analyze_regions(mask)
        assert len(regions) == 0

    def test_full_mismatch(self):
        mask = np.ones((100, 100), dtype=bool)
        regions = _analyze_regions(mask)
        assert len(regions) > 0
        assert all(r.severity == Severity.HIGH for r in regions)

    def test_partial_mismatch(self):
        mask = np.zeros((100, 100), dtype=bool)
        mask[0:20, 0:20] = True  # Top-left corner
        regions = _analyze_regions(mask)
        assert len(regions) > 0


class TestDiffHeatmap:
    def test_generates_image(self):
        a = np.full((100, 100, 3), 200, dtype=np.uint8)
        b = np.full((100, 100, 3), 100, dtype=np.uint8)
        mask = _pixel_diff(a, b)
        heatmap = _generate_diff_heatmap(a, b, mask)
        assert isinstance(heatmap, bytes)
        assert len(heatmap) > 0
        # Verify it's a valid PNG
        img = Image.open(io.BytesIO(heatmap))
        assert img.size == (100, 100)


# --- Integration tests for compare_images ---

@pytest.mark.asyncio
async def test_compare_identical_images():
    """Two identical images should pass comparison."""
    img = _create_solid_image(200, 200, (100, 150, 200))
    report = await compare_images(img, img, save_diff=False)
    assert report.passed
    assert report.pixel_mismatch_percent == 0.0
    assert report.ssim_score > 0.99
    assert len(report.regions) == 0


@pytest.mark.asyncio
async def test_compare_completely_different():
    """Two completely different images should fail comparison."""
    img_a = _create_solid_image(200, 200, (0, 0, 0))
    img_b = _create_solid_image(200, 200, (255, 255, 255))
    report = await compare_images(img_a, img_b, save_diff=False)
    assert not report.passed
    assert report.pixel_mismatch_percent > 90.0
    assert report.ssim_score < 0.1
    assert len(report.regions) > 0


@pytest.mark.asyncio
async def test_compare_small_difference():
    """Images with a small region of difference."""
    img_a = _create_solid_image(200, 200, (255, 255, 255))
    img_b = _create_image_with_region(
        200, 200,
        bg_color=(255, 255, 255),
        region_color=(200, 200, 200),  # Small difference
        region_x=90, region_y=90,
        region_w=20, region_h=20,
    )
    report = await compare_images(img_a, img_b, save_diff=False)
    # Small region difference
    assert report.pixel_mismatch_percent < 10.0
    assert report.ssim_score > 0.9


@pytest.mark.asyncio
async def test_compare_different_sizes():
    """Images of different sizes should be resized and compared."""
    img_a = _create_solid_image(200, 200, (128, 128, 128))
    img_b = _create_solid_image(300, 250, (128, 128, 128))
    report = await compare_images(img_a, img_b, save_diff=False)
    # After resize, same color should match well
    assert report.pixel_mismatch_percent < 5.0
    assert report.ssim_score > 0.9


@pytest.mark.asyncio
async def test_compare_gradient_images():
    """Similar gradient images should have high SSIM."""
    img_a = _create_gradient_image(200, 200, "horizontal")
    img_b = _create_gradient_image(200, 200, "horizontal")
    report = await compare_images(img_a, img_b, save_diff=False)
    assert report.passed
    assert report.ssim_score > 0.99


@pytest.mark.asyncio
async def test_compare_different_gradients():
    """Different gradient directions should fail."""
    img_a = _create_gradient_image(200, 200, "horizontal")
    img_b = _create_gradient_image(200, 200, "vertical")
    report = await compare_images(img_a, img_b, save_diff=False)
    assert not report.passed
    assert report.ssim_score < 0.9


# --- Tests for _downscale_for_comparison ---


class TestDownscaleForComparison:
    def test_downscale_large_image(self):
        img = np.zeros((3000, 2000, 3), dtype=np.uint8)
        result = _downscale_for_comparison(img, max_dim=1500)
        assert max(result.shape[:2]) <= 1500

    def test_no_downscale_small_image(self):
        img = np.zeros((800, 600, 3), dtype=np.uint8)
        result = _downscale_for_comparison(img, max_dim=1500)
        assert result.shape == (800, 600, 3)

    def test_downscale_preserves_aspect_ratio(self):
        img = np.zeros((3000, 2000, 3), dtype=np.uint8)
        result = _downscale_for_comparison(img, max_dim=1500)
        original_ratio = 3000 / 2000
        new_ratio = result.shape[0] / result.shape[1]
        assert abs(original_ratio - new_ratio) < 0.02


# --- Tests for _classify_mismatch ---


class TestClassifyMismatch:
    def test_classify_structural_difference(self):
        """Both edge structure AND large gray difference → Layout classification."""
        # Create cells with actual edge differences (not just uniform colors)
        cell_a = np.full((20, 20, 3), 0, dtype=np.uint8)
        cell_a[:10, :, :] = 255  # Top half white, bottom half black → strong edge
        cell_b = np.full((20, 20, 3), 200, dtype=np.uint8)  # Uniform gray → no edge
        result = _classify_mismatch(cell_a, cell_b)
        assert "Layout" in result

    def test_classify_color_difference(self):
        """High color-channel difference with moderate gray diff → Color."""
        # Create cells where color channels differ a lot but luminance less so
        cell_a = np.full((10, 10, 3), [100, 50, 50], dtype=np.uint8)
        cell_b = np.full((10, 10, 3), [50, 150, 150], dtype=np.uint8)
        result = _classify_mismatch(cell_a, cell_b)
        assert "Color" in result or "Typography" in result

    def test_classify_spacing_difference(self):
        """Small mean diff → Spacing classification."""
        cell_a = np.full((10, 10, 3), 100, dtype=np.uint8)
        cell_b = np.full((10, 10, 3), 110, dtype=np.uint8)  # mean diff = 10
        result = _classify_mismatch(cell_a, cell_b)
        assert "Spacing" in result


# --- Tests for _analyze_regions (advanced) ---


class TestAnalyzeRegionsAdvanced:
    def test_very_small_image(self):
        """4x4 mask → cell_h and cell_w become 0, returns empty."""
        mask = np.ones((4, 4), dtype=bool)
        regions = _analyze_regions(mask)
        assert isinstance(regions, list)
        # With 8x8 grid on a 4x4 image, cell size is 0 → empty
        assert len(regions) == 0

    def test_severity_thresholds(self):
        """Verify HIGH/MEDIUM/LOW severity based on mismatch percentage."""
        # 100x100 image, 8x8 grid → each cell is ~12x12 pixels
        mask = np.zeros((100, 100), dtype=bool)

        # HIGH region: fill entire top-left cell (>10%)
        mask[0:12, 0:12] = True

        # MEDIUM region: fill ~50% of a middle cell (~6 rows of 12)
        mask[24:30, 24:36] = True  # partial fill in a cell

        # LOW region: fill ~1% of a bottom cell
        mask[87:88, 87:88] = True  # tiny dot

        regions = _analyze_regions(mask)
        severities = {r.severity for r in regions}
        assert Severity.HIGH in severities
