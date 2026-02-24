"""Tests for the layout strategy agent's rules engine."""

import pytest

from agents.layout_strategy import (
    LayoutStrategyAgent,
    _analyze_node_layout,
    _detect_grid_pattern,
    _detect_overlap,
)
from schemas.design_spec import Bounds, DesignNode, DesignSpec, Layout
from schemas.layout_plan import LayoutStrategy


def _make_node(
    node_id: str = "1:1",
    name: str = "TestNode",
    node_type: str = "FRAME",
    x: float = 0,
    y: float = 0,
    width: float = 400,
    height: float = 300,
    children: list | None = None,
    layout_mode: str = "NONE",
    item_spacing: float = 0,
    primary_align: str = "MIN",
    counter_align: str = "MIN",
    layout_wrap: str = "NO_WRAP",
) -> DesignNode:
    """Helper to create a test DesignNode."""
    return DesignNode(
        id=node_id,
        name=name,
        type=node_type,
        bounds=Bounds(x=x, y=y, width=width, height=height),
        children=children or [],
        layout=Layout(
            mode=layout_mode,
            item_spacing=item_spacing,
            primary_axis_align=primary_align,
            counter_axis_align=counter_align,
            layout_wrap=layout_wrap,
        ),
    )


class TestOverlapDetection:
    def test_no_overlap(self):
        children = [
            _make_node("c1", x=0, y=0, width=100, height=50),
            _make_node("c2", x=120, y=0, width=100, height=50),
        ]
        assert not _detect_overlap(children)

    def test_overlap(self):
        children = [
            _make_node("c1", x=0, y=0, width=100, height=50),
            _make_node("c2", x=50, y=10, width=100, height=50),
        ]
        assert _detect_overlap(children)

    def test_single_child(self):
        children = [_make_node("c1")]
        assert not _detect_overlap(children)

    def test_empty(self):
        assert not _detect_overlap([])

    def test_adjacent_no_overlap(self):
        # Touching but not overlapping by more than 1px
        children = [
            _make_node("c1", x=0, y=0, width=100, height=50),
            _make_node("c2", x=100, y=0, width=100, height=50),
        ]
        assert not _detect_overlap(children)


class TestGridDetection:
    def test_grid_pattern(self):
        """4 items in a 2x2 grid should be detected."""
        children = [
            _make_node("c1", x=0, y=0, width=100, height=100),
            _make_node("c2", x=120, y=0, width=100, height=100),
            _make_node("c3", x=0, y=120, width=100, height=100),
            _make_node("c4", x=120, y=120, width=100, height=100),
        ]
        result = _detect_grid_pattern(children)
        assert result is not None
        assert result["rows"] == 2
        assert result["cols"] == 2

    def test_no_grid_horizontal(self):
        """Items in a single row are not a grid."""
        children = [
            _make_node("c1", x=0, y=0, width=100, height=100),
            _make_node("c2", x=120, y=0, width=100, height=100),
            _make_node("c3", x=240, y=0, width=100, height=100),
        ]
        result = _detect_grid_pattern(children)
        assert result is None  # Only 1 row

    def test_too_few_children(self):
        children = [
            _make_node("c1", x=0, y=0, width=100, height=100),
            _make_node("c2", x=120, y=0, width=100, height=100),
        ]
        result = _detect_grid_pattern(children)
        assert result is None


class TestAnalyzeNodeLayout:
    def test_auto_layout_horizontal(self):
        node = _make_node(
            layout_mode="HORIZONTAL",
            item_spacing=16,
            primary_align="CENTER",
            counter_align="CENTER",
        )
        decision = _analyze_node_layout(node)
        assert decision.strategy == LayoutStrategy.FLEX
        assert decision.flex_direction == "row"
        assert decision.justify_content == "center"
        assert decision.align_items == "center"
        assert decision.gap == "16px"

    def test_auto_layout_vertical(self):
        node = _make_node(
            layout_mode="VERTICAL",
            item_spacing=8,
            primary_align="SPACE_BETWEEN",
        )
        decision = _analyze_node_layout(node)
        assert decision.strategy == LayoutStrategy.FLEX
        assert decision.flex_direction == "column"
        assert decision.justify_content == "space-between"

    def test_auto_layout_wrap(self):
        node = _make_node(
            layout_mode="HORIZONTAL",
            layout_wrap="WRAP",
        )
        decision = _analyze_node_layout(node)
        assert decision.flex_wrap == "wrap"

    def test_single_child_block(self):
        child = _make_node("c1", node_type="RECTANGLE", x=10, y=10, width=50, height=50)
        node = _make_node(children=[child])
        decision = _analyze_node_layout(node)
        assert decision.strategy == LayoutStrategy.BLOCK

    def test_no_children_block(self):
        node = _make_node()
        decision = _analyze_node_layout(node)
        assert decision.strategy == LayoutStrategy.BLOCK

    def test_overlapping_children_absolute(self):
        children = [
            _make_node("c1", node_type="RECTANGLE", x=0, y=0, width=200, height=200),
            _make_node("c2", node_type="RECTANGLE", x=50, y=50, width=200, height=200),
        ]
        node = _make_node(children=children)
        decision = _analyze_node_layout(node)
        assert decision.strategy == LayoutStrategy.ABSOLUTE

    def test_horizontal_arrangement_flex_row(self):
        children = [
            _make_node("c1", node_type="RECTANGLE", x=0, y=0, width=100, height=50),
            _make_node("c2", node_type="RECTANGLE", x=120, y=0, width=100, height=50),
            _make_node("c3", node_type="RECTANGLE", x=240, y=0, width=100, height=50),
        ]
        node = _make_node(children=children)
        decision = _analyze_node_layout(node)
        assert decision.strategy == LayoutStrategy.FLEX
        assert decision.flex_direction == "row"

    def test_vertical_arrangement_flex_column(self):
        children = [
            _make_node("c1", node_type="RECTANGLE", x=0, y=0, width=200, height=50),
            _make_node("c2", node_type="RECTANGLE", x=0, y=70, width=200, height=50),
            _make_node("c3", node_type="RECTANGLE", x=0, y=140, width=200, height=50),
        ]
        node = _make_node(children=children)
        decision = _analyze_node_layout(node)
        assert decision.strategy == LayoutStrategy.FLEX
        assert decision.flex_direction == "column"

    def test_grid_detected(self):
        children = [
            _make_node("c1", node_type="RECTANGLE", x=0, y=0, width=100, height=100),
            _make_node("c2", node_type="RECTANGLE", x=120, y=0, width=100, height=100),
            _make_node("c3", node_type="RECTANGLE", x=0, y=120, width=100, height=100),
            _make_node("c4", node_type="RECTANGLE", x=120, y=120, width=100, height=100),
        ]
        node = _make_node(children=children)
        decision = _analyze_node_layout(node)
        assert decision.strategy == LayoutStrategy.GRID

    def test_invisible_children_ignored(self):
        visible_child = _make_node("c1", node_type="RECTANGLE", x=10, y=10, width=50, height=50)
        invisible_child = _make_node("c2", node_type="RECTANGLE", x=200, y=200, width=50, height=50)
        invisible_child.visible = False

        node = _make_node(children=[visible_child, invisible_child])
        decision = _analyze_node_layout(node)
        # Only one visible child → block
        assert decision.strategy == LayoutStrategy.BLOCK


@pytest.mark.asyncio
async def test_layout_strategy_agent_full():
    """Test the full agent execution with a sample design spec."""
    root = _make_node(
        "root",
        name="Root Frame",
        layout_mode="VERTICAL",
        item_spacing=24,
        children=[
            _make_node(
                "header",
                name="Header",
                layout_mode="HORIZONTAL",
                item_spacing=16,
                children=[
                    _make_node("logo", name="Logo", node_type="RECTANGLE", x=0, y=0, width=40, height=40),
                    _make_node("title", name="Title", node_type="TEXT", x=56, y=5, width=200, height=30),
                ],
            ),
            _make_node(
                "content",
                name="Content",
                children=[
                    _make_node("card1", node_type="RECTANGLE", x=0, y=0, width=200, height=150),
                    _make_node("card2", node_type="RECTANGLE", x=220, y=0, width=200, height=150),
                    _make_node("card3", node_type="RECTANGLE", x=0, y=170, width=200, height=150),
                    _make_node("card4", node_type="RECTANGLE", x=220, y=170, width=200, height=150),
                ],
            ),
        ],
    )

    spec = DesignSpec(root=root)
    agent = LayoutStrategyAgent(job_id="test-001")

    # Execute without GPT fallback to test pure rules engine
    plan = await agent.execute(design_spec=spec, use_gpt_fallback=False)

    # Root should be flex column (auto-layout VERTICAL)
    root_decision = plan.get_decision("root")
    assert root_decision is not None
    assert root_decision.strategy == LayoutStrategy.FLEX
    assert root_decision.flex_direction == "column"

    # Header should be flex row (auto-layout HORIZONTAL)
    header_decision = plan.get_decision("header")
    assert header_decision is not None
    assert header_decision.strategy == LayoutStrategy.FLEX
    assert header_decision.flex_direction == "row"

    # Content should be grid (2x2 pattern)
    content_decision = plan.get_decision("content")
    assert content_decision is not None
    assert content_decision.strategy == LayoutStrategy.GRID
