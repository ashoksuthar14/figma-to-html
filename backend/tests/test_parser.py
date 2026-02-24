"""Tests for Pydantic model parsing with sample design spec data."""

import pytest

from schemas.design_spec import (
    AssetReference,
    Bounds,
    Color,
    ComponentInfo,
    CornerRadius,
    DesignNode,
    DesignSpec,
    Effect,
    Fill,
    GradientStop,
    Layout,
    Metadata,
    Stroke,
    Style,
    TextInfo,
    TextSegment,
)
from schemas.diff_report import DiffRegion, DiffReport, Severity
from schemas.job import (
    JobCreate,
    JobResponse,
    JobResult,
    JobStatus,
    PluginDifference,
    PluginJobResult,
    PluginVerificationResult,
)
from schemas.layout_plan import LayoutDecision, LayoutPlan, LayoutStrategy


# --- Color model tests ---

class TestColor:
    def test_default_color(self):
        c = Color()
        assert c.r == 0.0
        assert c.g == 0.0
        assert c.b == 0.0
        assert c.a == 1.0

    def test_to_css_rgba_opaque(self):
        c = Color(r=1.0, g=0.5, b=0.0, a=1.0)
        assert c.to_css_rgba() == "rgb(255, 128, 0)"

    def test_to_css_rgba_transparent(self):
        c = Color(r=0.0, g=0.0, b=0.0, a=0.5)
        assert c.to_css_rgba() == "rgba(0, 0, 0, 0.5)"

    def test_to_css_hex_opaque(self):
        c = Color(r=1.0, g=1.0, b=1.0, a=1.0)
        assert c.to_css_hex() == "#ffffff"

    def test_to_css_hex_with_alpha(self):
        c = Color(r=1.0, g=0.0, b=0.0, a=0.5)
        result = c.to_css_hex()
        assert result.startswith("#ff0000")
        assert len(result) == 9  # includes alpha


# --- CornerRadius tests ---

class TestCornerRadius:
    def test_uniform_radius(self):
        cr = CornerRadius(top_left=8, top_right=8, bottom_right=8, bottom_left=8)
        assert cr.is_uniform
        assert cr.to_css() == "8px"

    def test_zero_radius(self):
        cr = CornerRadius()
        assert cr.is_uniform
        assert cr.to_css() == ""

    def test_mixed_radius(self):
        cr = CornerRadius(top_left=8, top_right=4, bottom_right=8, bottom_left=4)
        assert not cr.is_uniform
        assert cr.to_css() == "8px 4px 8px 4px"


# --- Fill model tests ---

class TestFill:
    def test_solid_fill(self):
        fill = Fill(
            type="SOLID",
            color=Color(r=0.2, g=0.4, b=0.6),
            opacity=1.0,
        )
        assert fill.type == "SOLID"
        assert fill.color is not None
        assert fill.visible

    def test_gradient_fill(self):
        fill = Fill(
            type="GRADIENT_LINEAR",
            gradient_stops=[
                GradientStop(position=0.0, color=Color(r=1.0)),
                GradientStop(position=1.0, color=Color(b=1.0)),
            ],
        )
        assert len(fill.gradient_stops) == 2


# --- DesignNode tests ---

class TestDesignNode:
    def _make_frame(self, node_id="1:1", children=None) -> DesignNode:
        return DesignNode(
            id=node_id,
            name="Test Frame",
            type="FRAME",
            bounds=Bounds(x=0, y=0, width=400, height=300),
            children=children or [],
        )

    def _make_text(self, node_id="1:2") -> DesignNode:
        return DesignNode(
            id=node_id,
            name="Test Text",
            type="TEXT",
            bounds=Bounds(x=10, y=10, width=100, height=20),
            text=TextInfo(
                characters="Hello World",
                segments=[
                    TextSegment(
                        characters="Hello World",
                        font_family="Inter",
                        font_size=16,
                        font_weight=400,
                    )
                ],
            ),
        )

    def test_is_container(self):
        frame = self._make_frame()
        assert frame.is_container()

        text = self._make_text()
        assert not text.is_container()

    def test_has_auto_layout(self):
        frame = self._make_frame()
        assert not frame.has_auto_layout()

        frame.layout = Layout(mode="HORIZONTAL")
        assert frame.has_auto_layout()

    def test_get_all_descendants(self):
        child1 = self._make_text("1:2")
        child2 = self._make_text("1:3")
        grandchild = self._make_text("1:4")
        inner_frame = self._make_frame("1:5", children=[grandchild])
        root = self._make_frame("1:1", children=[child1, child2, inner_frame])

        descendants = root.get_all_descendants()
        ids = {d.id for d in descendants}
        assert ids == {"1:2", "1:3", "1:5", "1:4"}
        assert len(descendants) == 4


# --- Full DesignSpec parsing test ---

class TestDesignSpec:
    def test_parse_minimal_spec(self):
        spec = DesignSpec(
            root=DesignNode(
                id="0:1",
                name="Root",
                type="FRAME",
                bounds=Bounds(width=1440, height=900),
            ),
        )
        assert spec.root.id == "0:1"
        assert spec.root.bounds.width == 1440
        assert spec.metadata.file_key == ""

    def test_parse_full_spec(self):
        data = {
            "metadata": {
                "file_key": "abc123",
                "file_name": "Test File",
                "frame_id": "1:1",
                "frame_name": "Homepage",
                "exported_at": "2024-01-01T00:00:00Z",
                "plugin_version": "1.0.0",
                "figma_schema_version": "1",
            },
            "root": {
                "id": "1:1",
                "name": "Homepage",
                "type": "FRAME",
                "bounds": {"x": 0, "y": 0, "width": 1440, "height": 900},
                "style": {
                    "fills": [
                        {"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}
                    ],
                    "opacity": 1.0,
                },
                "layout": {
                    "mode": "VERTICAL",
                    "padding_top": 20,
                    "padding_right": 40,
                    "padding_bottom": 20,
                    "padding_left": 40,
                    "item_spacing": 24,
                    "primary_axis_align": "MIN",
                    "counter_axis_align": "CENTER",
                },
                "children": [
                    {
                        "id": "1:2",
                        "name": "Header",
                        "type": "FRAME",
                        "bounds": {"x": 0, "y": 0, "width": 1440, "height": 80},
                        "layout": {"mode": "HORIZONTAL", "item_spacing": 16},
                        "children": [
                            {
                                "id": "1:3",
                                "name": "Logo",
                                "type": "RECTANGLE",
                                "bounds": {"x": 40, "y": 20, "width": 120, "height": 40},
                                "style": {
                                    "corner_radius": {
                                        "top_left": 4,
                                        "top_right": 4,
                                        "bottom_right": 4,
                                        "bottom_left": 4,
                                    }
                                },
                            },
                            {
                                "id": "1:4",
                                "name": "Title",
                                "type": "TEXT",
                                "bounds": {"x": 180, "y": 25, "width": 200, "height": 30},
                                "text": {
                                    "characters": "My Website",
                                    "segments": [
                                        {
                                            "characters": "My Website",
                                            "font_family": "Inter",
                                            "font_weight": 700,
                                            "font_size": 24,
                                            "line_height": 30,
                                        }
                                    ],
                                    "text_align_horizontal": "LEFT",
                                },
                            },
                        ],
                    },
                ],
            },
            "fonts_used": ["Inter"],
            "color_palette": [
                {"r": 1, "g": 1, "b": 1, "a": 1},
                {"r": 0, "g": 0, "b": 0, "a": 1},
            ],
        }

        spec = DesignSpec.model_validate(data)
        assert spec.metadata.file_key == "abc123"
        assert spec.root.name == "Homepage"
        assert spec.root.has_auto_layout()
        assert len(spec.root.children) == 1
        header = spec.root.children[0]
        assert header.name == "Header"
        assert header.layout.mode == "HORIZONTAL"
        assert len(header.children) == 2
        assert header.children[1].text is not None
        assert header.children[1].text.characters == "My Website"
        assert len(spec.fonts_used) == 1
        assert len(spec.color_palette) == 2


# --- Layout Plan tests ---

class TestLayoutPlan:
    def test_layout_decision(self):
        d = LayoutDecision(
            node_id="1:1",
            strategy=LayoutStrategy.FLEX,
            flex_direction="row",
            justify_content="center",
            align_items="center",
            gap="16px",
        )
        assert d.strategy == LayoutStrategy.FLEX
        assert d.flex_direction == "row"

    def test_layout_plan_operations(self):
        plan = LayoutPlan()
        d1 = LayoutDecision(node_id="1:1", strategy=LayoutStrategy.FLEX)
        d2 = LayoutDecision(node_id="1:2", strategy=LayoutStrategy.GRID)

        plan.set_decision(d1)
        plan.set_decision(d2)

        assert plan.get_decision("1:1") is not None
        assert plan.get_decision("1:1").strategy == LayoutStrategy.FLEX
        assert plan.get_decision("1:2").strategy == LayoutStrategy.GRID
        assert plan.get_decision("1:99") is None


# --- DiffReport tests ---

class TestDiffReport:
    def test_diff_report_passed(self):
        report = DiffReport(
            passed=True,
            pixel_mismatch_percent=0.1,
            ssim_score=0.99,
        )
        assert report.passed
        assert "PASSED" in report.summary

    def test_diff_report_failed_with_regions(self):
        report = DiffReport(
            passed=False,
            pixel_mismatch_percent=5.5,
            ssim_score=0.85,
            regions=[
                DiffRegion(
                    area=100,
                    issue="Color mismatch",
                    severity=Severity.HIGH,
                    mismatch_percent=15.0,
                ),
                DiffRegion(
                    area=50,
                    issue="Spacing difference",
                    severity=Severity.LOW,
                    mismatch_percent=2.0,
                ),
            ],
        )
        assert not report.passed
        assert len(report.high_severity_regions) == 1
        assert "FAILED" in report.summary


# --- Job models tests ---

class TestJobModels:
    def test_job_status_enum(self):
        assert JobStatus.QUEUED.value == "queued"
        assert JobStatus.PROCESSING.value == "processing"
        assert JobStatus.VERIFYING.value == "verifying"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"

    def test_job_create(self):
        spec = DesignSpec(
            root=DesignNode(id="0:1", name="Root", type="FRAME"),
        )
        job = JobCreate(
            design_spec=spec,
            figma_file_key="abc123",
        )
        assert job.figma_file_key == "abc123"

    def test_job_response(self):
        resp = JobResponse(
            job_id="test-123",
            status=JobStatus.PROCESSING,
        )
        assert resp.job_id == "test-123"
        assert resp.result is None
        assert resp.error is None
        assert resp.progress == 0
        assert resp.current_step == ""
        assert resp.completed_at is None

    def test_job_response_defaults_to_queued(self):
        resp = JobResponse(job_id="test-456")
        assert resp.status == JobStatus.QUEUED
        assert resp.progress == 0


class TestPluginModels:
    def test_plugin_verification_from_diff_report(self):
        report = DiffReport(
            passed=False,
            pixel_mismatch_percent=5.5,
            ssim_score=0.85,
            diff_image_path="/tmp/diff.png",
            regions=[
                DiffRegion(
                    area=100,
                    issue="Color mismatch in header",
                    severity=Severity.HIGH,
                    mismatch_percent=15.0,
                ),
                DiffRegion(
                    area=50,
                    issue="Spacing difference in footer",
                    severity=Severity.LOW,
                    mismatch_percent=2.0,
                ),
            ],
        )
        result = PluginVerificationResult.from_diff_report(
            report, base_url="http://localhost:8000", job_id="job-1"
        )
        # overall = ssim*50 + (100 - mismatch)*0.5 => 0.85*50 + 94.5*0.5 = 89.75
        assert result.overall_score == 89.8
        assert result.color_score < result.overall_score  # penalized by "Color mismatch"
        assert result.spacing_score < result.overall_score  # penalized by "Spacing difference"
        assert len(result.differences) == 2
        assert result.differences[0].severity == "high"
        assert result.differences[1].issue == "Spacing difference in footer"
        assert result.comparison_image_url == "http://localhost:8000/jobs/job-1/diff-image"

    def test_plugin_verification_no_regions(self):
        report = DiffReport(
            passed=True,
            pixel_mismatch_percent=0.1,
            ssim_score=0.99,
        )
        result = PluginVerificationResult.from_diff_report(report)
        # overall = ssim*50 + (100 - mismatch)*0.5 => 0.99*50 + 99.9*0.5 = 99.45
        assert result.overall_score == 99.5
        assert result.layout_score == 99.5
        assert result.color_score == 99.5
        assert result.typography_score == 99.5
        assert result.spacing_score == 99.5
        assert result.differences == []
        assert result.comparison_image_url is None

    def test_plugin_job_result_from_internal(self):
        internal = JobResult(
            job_id="job-1",
            html_content="<div>test</div>",
            css_content=".test { color: red; }",
            verification=DiffReport(
                passed=True,
                pixel_mismatch_percent=0.1,
                ssim_score=0.98,
            ),
        )
        result = PluginJobResult.from_internal(
            internal, base_url="http://localhost:8000", job_id="job-1"
        )
        assert result.html_url == "http://localhost:8000/jobs/job-1/html"
        assert result.css_url == "http://localhost:8000/jobs/job-1/css"
        assert result.zip_url == "http://localhost:8000/jobs/job-1/download"
        assert result.preview_url == "http://localhost:8000/jobs/job-1/preview"
        assert result.verification is not None
        # overall = ssim*50 + (100 - mismatch)*0.5 => 0.98*50 + 99.9*0.5 = 98.95
        assert result.verification.overall_score == 99.0

    def test_plugin_job_result_camel_case_serialization(self):
        internal = JobResult(
            job_id="job-1",
            html_content="<div></div>",
            css_content="",
        )
        result = PluginJobResult.from_internal(
            internal, base_url="http://localhost:8000", job_id="job-1"
        )
        data = result.model_dump(by_alias=True)
        assert "htmlUrl" in data
        assert "cssUrl" in data
        assert "zipUrl" in data
        assert "previewUrl" in data


# --- Plugin field compatibility tests ---

class TestAssetReferencePluginFormat:
    """Test that AssetReference accepts both plugin and backend field names."""

    def test_plugin_format_nodename_and_data(self):
        """Plugin sends nodeName + data; should map to filename + data_base64."""
        asset = AssetReference.model_validate({
            "nodeId": "1:1",
            "nodeName": "perfume-bottle",
            "data": "iVBORw0KGgo...",
        })
        assert asset.filename == "perfume-bottle-1-1.png"
        assert asset.data_base64 == "iVBORw0KGgo..."
        assert asset.node_id == "1:1"

    def test_plugin_format_nodename_with_extension(self):
        """If nodeName already has an extension, don't double-add .png."""
        asset = AssetReference.model_validate({
            "nodeId": "1:2",
            "nodeName": "logo.svg",
            "data": "PHN2Zy...",
        })
        assert asset.filename == "logo-1-2.svg"

    def test_backend_format_still_works(self):
        """Backend-native format (filename + data_base64) must keep working."""
        asset = AssetReference.model_validate({
            "nodeId": "1:3",
            "filename": "cart-icon.png",
            "dataBase64": "abc123==",
        })
        assert asset.filename == "cart-icon-1-3.png"
        assert asset.data_base64 == "abc123=="

    def test_backend_snake_case_format(self):
        """Snake_case field names must keep working."""
        asset = AssetReference.model_validate({
            "node_id": "1:4",
            "filename": "hero.png",
            "data_base64": "xyz==",
        })
        assert asset.node_id == "1:4"
        assert asset.filename == "hero-1-4.png"
        assert asset.data_base64 == "xyz=="


class TestTextSegmentPluginFormat:
    """Test that TextSegment accepts bare 'color' dict from the plugin."""

    def test_plugin_color_to_fill(self):
        """Plugin sends color: {r,g,b,a} directly; should become fill.color."""
        seg = TextSegment.model_validate({
            "characters": "luxury",
            "fontFamily": "Playfair Display",
            "fontWeight": 700,
            "fontSize": 48,
            "color": {"r": 0.9, "g": 0.4, "b": 0.7, "a": 1.0},
        })
        assert seg.fill is not None
        assert seg.fill.type == "SOLID"
        assert seg.fill.color is not None
        assert seg.fill.color.r == 0.9
        assert seg.fill.color.g == 0.4

    def test_backend_fill_format_still_works(self):
        """Backend format (fill: {type, color}) must keep working."""
        seg = TextSegment.model_validate({
            "characters": "Hello",
            "fill": {
                "type": "SOLID",
                "color": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0},
            },
        })
        assert seg.fill is not None
        assert seg.fill.color.r == 1.0

    def test_no_color_no_fill(self):
        """When neither color nor fill is provided, fill remains None."""
        seg = TextSegment.model_validate({
            "characters": "plain text",
        })
        assert seg.fill is None

    def test_line_height_auto_still_works(self):
        """lineHeight: 'auto' normalization must still work alongside color fix."""
        seg = TextSegment.model_validate({
            "characters": "test",
            "lineHeight": "auto",
            "color": {"r": 0.5, "g": 0.5, "b": 0.5, "a": 1.0},
        })
        assert seg.line_height is None
        assert seg.fill is not None
        assert seg.fill.color.r == 0.5


class TestEffectPluginFormat:
    """Test that Effect accepts offsetX/offsetY from the plugin."""

    def test_plugin_offset_xy(self):
        """Plugin sends offsetX/offsetY; should map to offset: {x, y}."""
        eff = Effect.model_validate({
            "type": "DROP_SHADOW",
            "offsetX": 4,
            "offsetY": 8,
            "radius": 12,
            "spread": 2,
            "color": {"r": 0, "g": 0, "b": 0, "a": 0.25},
        })
        assert eff.offset == {"x": 4.0, "y": 8.0}
        assert eff.radius == 12
        assert eff.spread == 2
        assert eff.color is not None
        assert eff.color.a == 0.25

    def test_backend_offset_dict_still_works(self):
        """Backend format (offset: {x, y}) must keep working."""
        eff = Effect.model_validate({
            "type": "DROP_SHADOW",
            "offset": {"x": 2, "y": 4},
            "radius": 6,
        })
        assert eff.offset == {"x": 2, "y": 4}

    def test_inner_shadow_with_plugin_format(self):
        """INNER_SHADOW with plugin-format offset."""
        eff = Effect.model_validate({
            "type": "INNER_SHADOW",
            "offsetX": 0,
            "offsetY": 2,
            "radius": 4,
            "color": {"r": 0, "g": 0, "b": 0, "a": 0.1},
        })
        assert eff.type == "INNER_SHADOW"
        assert eff.offset == {"x": 0.0, "y": 2.0}


class TestFillGradientAngle:
    """Test gradient angle computation from transform matrix and handle positions."""

    def test_angle_from_gradient_transform_vertical(self):
        """Identity-like transform → 180deg (top to bottom)."""
        fill = Fill(
            type="GRADIENT_LINEAR",
            gradient_transform=[[0, 1, 0], [1, 0, 0]],
            gradient_stops=[
                GradientStop(position=0.0, color=Color(r=1.0)),
                GradientStop(position=1.0, color=Color(b=1.0)),
            ],
        )
        angle = fill.gradient_angle_deg()
        assert angle is not None

    def test_angle_from_handle_positions_fallback(self):
        """When no gradient_transform, fall back to handle positions."""
        fill = Fill(
            type="GRADIENT_LINEAR",
            gradient_handle_positions=[
                {"x": 0.0, "y": 0.0},
                {"x": 1.0, "y": 0.0},
            ],
            gradient_stops=[
                GradientStop(position=0.0, color=Color(r=1.0)),
                GradientStop(position=1.0, color=Color(b=1.0)),
            ],
        )
        angle = fill.gradient_angle_deg()
        assert angle is not None
        # Left-to-right → 90deg
        assert angle == 90.0

class TestDesignSpecFrameScreenshot:
    """Test that DesignSpec accepts the frameScreenshot field from the plugin."""

    def test_frame_screenshot_from_plugin_camel_case(self):
        """Plugin sends frameScreenshot (camelCase); should map to frame_screenshot."""
        data = {
            "root": {
                "id": "0:1",
                "name": "Root",
                "type": "FRAME",
            },
            "frameScreenshot": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ",
        }
        spec = DesignSpec.model_validate(data)
        assert spec.frame_screenshot == "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"

    def test_frame_screenshot_snake_case(self):
        """Backend-native snake_case field name should also work."""
        data = {
            "root": {
                "id": "0:1",
                "name": "Root",
                "type": "FRAME",
            },
            "frame_screenshot": "abc123base64==",
        }
        spec = DesignSpec.model_validate(data)
        assert spec.frame_screenshot == "abc123base64=="

    def test_frame_screenshot_defaults_to_none(self):
        """When no screenshot is provided, field should be None."""
        spec = DesignSpec(
            root=DesignNode(id="0:1", name="Root", type="FRAME"),
        )
        assert spec.frame_screenshot is None

    def test_frame_screenshot_serializes_as_camel_case(self):
        """When serialized with by_alias=True, field should be frameScreenshot."""
        spec = DesignSpec(
            root=DesignNode(id="0:1", name="Root", type="FRAME"),
            frame_screenshot="test_data",
        )
        data = spec.model_dump(by_alias=True)
        assert "frameScreenshot" in data
        assert data["frameScreenshot"] == "test_data"


class TestFillGradientAngleNoData:
    def test_no_transform_no_handles(self):
        """When neither transform nor handles exist, return None."""
        fill = Fill(
            type="GRADIENT_LINEAR",
            gradient_stops=[
                GradientStop(position=0.0, color=Color(r=1.0)),
                GradientStop(position=1.0, color=Color(b=1.0)),
            ],
        )
        assert fill.gradient_angle_deg() is None
