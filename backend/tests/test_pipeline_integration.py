"""Integration tests for asset saving, verification screenshot copying, and fix loop state."""

import base64
import logging
import shutil
from pathlib import Path

from schemas.design_spec import AssetReference
from schemas.diff_report import DiffReport


# ---------------------------------------------------------------------------
# TestAssetSavingToDisk – validates base64 asset decode & save logic
# (mirrors the logic in routers/jobs.py lines 154-170)
# ---------------------------------------------------------------------------


class TestAssetSavingToDisk:
    """Test the base64 asset decode-and-save workflow."""

    @staticmethod
    def _save_assets(assets: list[AssetReference], asset_dir: Path, job_id: str = "test-job"):
        """Reproduce the asset-saving logic from routers/jobs.py."""
        asset_dir.mkdir(parents=True, exist_ok=True)
        for asset in assets:
            if asset.data_base64:
                try:
                    data = base64.b64decode(asset.data_base64)
                    file_path = asset_dir / asset.filename
                    file_path.write_bytes(data)
                    asset.url = f"assets/{asset.filename}"
                except Exception:
                    logging.warning("Failed to decode base64 asset %s", asset.filename)

    def test_base64_asset_decoded_and_saved(self, tmp_path: Path):
        raw = b"hello world"
        b64 = base64.b64encode(raw).decode()
        asset = AssetReference(node_id="1:1", filename="test.png", data_base64=b64)
        asset_dir = tmp_path / "assets"
        self._save_assets([asset], asset_dir)

        saved = asset_dir / asset.filename
        assert saved.exists()
        assert saved.read_bytes() == raw

    def test_asset_saved_with_unique_filename(self, tmp_path: Path):
        b64 = base64.b64encode(b"x").decode()
        asset = AssetReference(**{
            "nodeName": "Vector",
            "nodeId": "1:403",
            "data": b64,
        })
        asset_dir = tmp_path / "assets"
        self._save_assets([asset], asset_dir)

        saved = asset_dir / asset.filename
        assert saved.exists()
        assert "1-403" in asset.filename

    def test_corrupt_base64_handled_gracefully(self, tmp_path: Path, caplog):
        asset = AssetReference(node_id="1:2", filename="bad.png", data_base64="!!!NOT-BASE64!!!")
        asset_dir = tmp_path / "assets"
        with caplog.at_level(logging.WARNING):
            self._save_assets([asset], asset_dir)
        # Should not crash; file should not exist
        assert not (asset_dir / asset.filename).exists()

    def test_multiple_assets_saved_to_correct_directory(self, tmp_path: Path):
        asset_dir = tmp_path / "assets"
        assets = []
        for i in range(3):
            b64 = base64.b64encode(f"data{i}".encode()).decode()
            assets.append(AssetReference(
                node_id=f"1:{i}",
                filename=f"img{i}.png",
                data_base64=b64,
            ))
        self._save_assets(assets, asset_dir)
        saved_files = list(asset_dir.iterdir())
        assert len(saved_files) == 3

    def test_asset_url_set_after_save(self, tmp_path: Path):
        b64 = base64.b64encode(b"px").decode()
        asset = AssetReference(node_id="5:1", filename="pic.png", data_base64=b64)
        asset_dir = tmp_path / "assets"
        self._save_assets([asset], asset_dir, job_id="j42")
        assert asset.url is not None
        assert asset.url.startswith("assets/")


# ---------------------------------------------------------------------------
# TestVerificationScreenshotCopying – mirrors orchestrator.py lines 448-456
# ---------------------------------------------------------------------------


class TestVerificationScreenshotCopying:
    """Test that verification screenshots are copied from temp to output."""

    SCREENSHOT_NAMES = ("figma_screenshot.png", "rendered_screenshot.png", "diff_heatmap.png")

    @staticmethod
    def _copy_screenshots(temp_job_dir: Path, output_dir: Path):
        """Reproduce the screenshot-copying logic from orchestrator.py."""
        verification_dst = output_dir / "verification"
        verification_dst.mkdir(parents=True, exist_ok=True)
        for screenshot_name in ("figma_screenshot.png", "rendered_screenshot.png", "diff_heatmap.png"):
            src = temp_job_dir / screenshot_name
            if src.exists():
                shutil.copy2(src, verification_dst / screenshot_name)

    def test_all_three_screenshots_copied(self, tmp_path: Path):
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        for name in self.SCREENSHOT_NAMES:
            (temp_dir / name).write_bytes(b"PNG")

        output_dir = tmp_path / "output"
        self._copy_screenshots(temp_dir, output_dir)

        ver_dir = output_dir / "verification"
        assert ver_dir.exists()
        for name in self.SCREENSHOT_NAMES:
            assert (ver_dir / name).exists()

    def test_missing_source_screenshot_no_crash(self, tmp_path: Path):
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        # Only create one of three
        (temp_dir / "figma_screenshot.png").write_bytes(b"PNG")

        output_dir = tmp_path / "output"
        self._copy_screenshots(temp_dir, output_dir)

        ver_dir = output_dir / "verification"
        assert (ver_dir / "figma_screenshot.png").exists()
        assert not (ver_dir / "rendered_screenshot.png").exists()

    def test_verification_dir_created_when_absent(self, tmp_path: Path):
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        (temp_dir / "diff_heatmap.png").write_bytes(b"PNG")

        output_dir = tmp_path / "output"
        assert not output_dir.exists()
        self._copy_screenshots(temp_dir, output_dir)
        assert (output_dir / "verification").is_dir()

    def test_no_screenshots_no_crash(self, tmp_path: Path):
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()  # empty
        output_dir = tmp_path / "output"
        self._copy_screenshots(temp_dir, output_dir)
        # Should not crash; verification dir created but empty of screenshots
        ver_dir = output_dir / "verification"
        assert ver_dir.is_dir()
        assert len(list(ver_dir.iterdir())) == 0


# ---------------------------------------------------------------------------
# TestFixLoopStateManagement – unit tests for fix-loop state tracking
# (mirrors orchestrator.py lines 236-367)
# ---------------------------------------------------------------------------


def _make_report(*, passed: bool = False, ssim: float = 0.5, mismatch: float = 50.0) -> DiffReport:
    return DiffReport(
        passed=passed,
        ssim_score=ssim,
        pixel_mismatch_percent=mismatch,
        total_pixels=10000,
        mismatched_pixels=int(mismatch * 100),
    )


def _run_fix_loop(
    initial_html: str,
    initial_css: str,
    initial_report: DiffReport,
    fix_results: list[dict],
    verify_reports: list[DiffReport],
    allow_html_fixes: bool = False,
) -> dict:
    """Simulate the fix loop logic from orchestrator.py without async/agents."""
    best_html = initial_html
    best_css = initial_css
    best_report = initial_report
    best_ssim = initial_report.ssim_score
    best_mismatch = initial_report.pixel_mismatch_percent

    html_content = initial_html
    current_css = initial_css
    current_report = initial_report
    iterations_used = 0

    for iteration in range(len(fix_results)):
        iterations_used = iteration + 1
        fix_result = fix_results[iteration]
        new_report = verify_reports[iteration]

        fixed_css = fix_result["css"]
        fixed_html = fix_result.get("html")

        improved = (
            new_report.ssim_score > current_report.ssim_score
            or new_report.pixel_mismatch_percent < current_report.pixel_mismatch_percent
        )

        if improved:
            current_css = fixed_css
            current_report = new_report
            if fixed_html and allow_html_fixes:
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

            if new_report.passed:
                break

    return {
        "html": best_html,
        "css": best_css,
        "report": best_report,
        "ssim": best_ssim,
        "mismatch": best_mismatch,
        "iterations": iterations_used,
    }


class TestFixLoopStateManagement:
    """Validate fix loop best-result tracking, rollback, and early exit."""

    def test_best_result_tracking_across_iterations(self):
        initial = _make_report(ssim=0.50, mismatch=50.0)
        result = _run_fix_loop(
            "html", "css",
            initial,
            fix_results=[
                {"css": "css1"},
                {"css": "css2"},
                {"css": "css3"},
            ],
            verify_reports=[
                _make_report(ssim=0.60, mismatch=40.0),
                _make_report(ssim=0.80, mismatch=20.0),  # best
                _make_report(ssim=0.70, mismatch=30.0),  # worse than iter 2
            ],
        )
        assert result["css"] == "css2"
        assert result["ssim"] == 0.80

    def test_rollback_when_fix_degrades_quality(self):
        initial = _make_report(ssim=0.70, mismatch=30.0)
        result = _run_fix_loop(
            "html", "css",
            initial,
            fix_results=[
                {"css": "worse_css"},
            ],
            verify_reports=[
                _make_report(ssim=0.50, mismatch=50.0),  # worse
            ],
        )
        # Best should still be the initial
        assert result["css"] == "css"
        assert result["ssim"] == 0.70

    def test_early_exit_when_verification_passes(self):
        initial = _make_report(ssim=0.50, mismatch=50.0)
        result = _run_fix_loop(
            "html", "css",
            initial,
            fix_results=[
                {"css": "css1"},
                {"css": "css2"},  # should never be reached
            ],
            verify_reports=[
                _make_report(passed=True, ssim=0.99, mismatch=0.1),
                _make_report(ssim=0.60, mismatch=40.0),  # should not matter
            ],
        )
        assert result["iterations"] == 1
        assert result["report"].passed is True

    def test_best_result_used_when_no_iteration_passes(self):
        initial = _make_report(ssim=0.40, mismatch=60.0)
        result = _run_fix_loop(
            "html", "css",
            initial,
            fix_results=[
                {"css": "css1"},
                {"css": "css2"},
            ],
            verify_reports=[
                _make_report(ssim=0.55, mismatch=45.0),
                _make_report(ssim=0.65, mismatch=35.0),
            ],
        )
        # Neither passed, but best should be iteration 2
        assert result["css"] == "css2"
        assert result["ssim"] == 0.65
        assert result["report"].passed is False

    def test_html_updated_when_fixer_provides_html(self):
        initial = _make_report(ssim=0.50, mismatch=50.0)
        result = _run_fix_loop(
            "original_html", "css",
            initial,
            fix_results=[
                {"css": "new_css", "html": "new_html"},
            ],
            verify_reports=[
                _make_report(ssim=0.80, mismatch=20.0),
            ],
            allow_html_fixes=True,
        )
        assert result["html"] == "new_html"
        assert result["css"] == "new_css"
