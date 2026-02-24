"""Agent 2 - Layout Strategy: Determines CSS layout approach for each container node."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

from agents.base import BaseAgent
from schemas.design_spec import Bounds, DesignNode, DesignSpec
from schemas.layout_plan import LayoutDecision, LayoutPlan, LayoutStrategy
from services.openai_service import call_gpt4

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _fmt_px(v: float) -> str:
    """Format a pixel value, using integer form when there's no fractional part."""
    return f"{int(v)}px" if v == int(v) else f"{v}px"


def _map_figma_align_to_css_justify(align: str) -> str:
    """Map Figma primary axis alignment to CSS justify-content."""
    mapping = {
        "MIN": "flex-start",
        "CENTER": "center",
        "MAX": "flex-end",
        "SPACE_BETWEEN": "space-between",
    }
    return mapping.get(align, "flex-start")


def _map_figma_align_to_css_align(align: str) -> str:
    """Map Figma counter axis alignment to CSS align-items."""
    mapping = {
        "MIN": "flex-start",
        "CENTER": "center",
        "MAX": "flex-end",
        "BASELINE": "baseline",
    }
    return mapping.get(align, "stretch")


def _detect_overlap(children: list[DesignNode]) -> bool:
    """Check if any children overlap each other."""
    if len(children) < 2:
        return False

    for i in range(len(children)):
        for j in range(i + 1, len(children)):
            a = children[i].bounds
            b = children[j].bounds

            # Check for bounding box overlap
            if (
                a.x < b.x + b.width
                and a.x + a.width > b.x
                and a.y < b.y + b.height
                and a.y + a.height > b.y
            ):
                # Overlaps by at least 1px in both axes
                overlap_x = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
                overlap_y = min(a.y + a.height, b.y + b.height) - max(a.y, b.y)
                if overlap_x > 1 and overlap_y > 1:
                    return True
    return False


def _detect_grid_pattern(children: list[DesignNode]) -> Optional[dict]:
    """Detect if children form a grid pattern.

    Returns grid info dict if detected, None otherwise.
    """
    if len(children) < 4:
        return None

    # Collect unique Y positions (rows) and X positions (columns)
    tolerance = 2.0  # pixel tolerance for alignment

    y_positions: list[float] = []
    for child in children:
        y = child.bounds.y
        found = False
        for existing_y in y_positions:
            if abs(y - existing_y) <= tolerance:
                found = True
                break
        if not found:
            y_positions.append(y)

    x_positions: list[float] = []
    for child in children:
        x = child.bounds.x
        found = False
        for existing_x in x_positions:
            if abs(x - existing_x) <= tolerance:
                found = True
                break
        if not found:
            x_positions.append(x)

    y_positions.sort()
    x_positions.sort()

    num_rows = len(y_positions)
    num_cols = len(x_positions)

    # Need at least 2 rows and 2 columns for a grid
    if num_rows < 2 or num_cols < 2:
        return None

    # Check that most children fit into the grid cells
    expected_cells = num_rows * num_cols
    if len(children) < expected_cells * 0.7:
        # Too many empty cells, probably not a grid
        return None

    # Check for consistent column widths
    child_widths: list[float] = [c.bounds.width for c in children]
    if child_widths:
        avg_width = sum(child_widths) / len(child_widths)
        width_variance = sum((w - avg_width) ** 2 for w in child_widths) / len(child_widths)
        # Allow some variance but widths should be roughly consistent
        if width_variance > (avg_width * 0.3) ** 2:
            return None

    # Compute column gaps
    if num_cols >= 2:
        col_gap = (x_positions[-1] - x_positions[0]) / (num_cols - 1) - avg_width
        col_gap = max(0, col_gap)
    else:
        col_gap = 0

    return {
        "rows": num_rows,
        "cols": num_cols,
        "col_gap": round(col_gap),
        "avg_width": round(avg_width),
    }


def _is_within_root(child: DesignNode, root_bounds: Bounds | None) -> bool:
    """Return True if *child* overlaps the root frame (i.e. is not entirely outside)."""
    if root_bounds is None:
        return True
    nb = child.bounds
    rb = root_bounds
    if nb.x >= rb.x + rb.width or nb.x + nb.width <= rb.x:
        return False
    if nb.y >= rb.y + rb.height or nb.y + nb.height <= rb.y:
        return False
    return True


def _analyze_node_layout(
    node: DesignNode,
    root_bounds: Bounds | None = None,
) -> LayoutDecision:
    """Apply the rules engine to determine layout strategy for a single container node."""

    # Rule 1: Auto-layout nodes map directly to flexbox
    if node.has_auto_layout():
        direction = "row" if node.layout.mode == "HORIZONTAL" else "column"
        justify = _map_figma_align_to_css_justify(node.layout.primary_axis_align)
        align = _map_figma_align_to_css_align(node.layout.counter_axis_align)
        gap = _fmt_px(node.layout.item_spacing) if node.layout.item_spacing > 0 else None
        wrap = "wrap" if node.layout.layout_wrap == "WRAP" else None

        return LayoutDecision(
            node_id=node.id,
            strategy=LayoutStrategy.FLEX,
            flex_direction=direction,
            justify_content=justify,
            align_items=align,
            gap=gap,
            flex_wrap=wrap,
            notes=f"Auto-layout {node.layout.mode} mapped to flexbox",
        )

    visible_children = [
        c for c in node.children
        if c.visible and _is_within_root(c, root_bounds)
    ]

    # Rule 2: No children or single child → block
    if len(visible_children) <= 1:
        return LayoutDecision(
            node_id=node.id,
            strategy=LayoutStrategy.BLOCK,
            notes="Single or no children, using block layout",
        )

    # Rule 3: Non-auto-layout containers use absolute positioning.
    # When Figma's layout.mode is "NONE", children are placed at explicit
    # coordinates.  Flex/grid heuristics lose the exact gaps and offsets.
    if not node.has_auto_layout():
        return LayoutDecision(
            node_id=node.id,
            strategy=LayoutStrategy.ABSOLUTE,
            notes="Non-auto-layout container; preserving Figma absolute coordinates",
        )

    # Rule 4: Overlapping children → absolute positioning
    if _detect_overlap(visible_children):
        return LayoutDecision(
            node_id=node.id,
            strategy=LayoutStrategy.ABSOLUTE,
            notes="Overlapping children detected, using absolute positioning",
        )

    # Rule 5: Grid pattern detection
    grid_info = _detect_grid_pattern(visible_children)
    if grid_info:
        cols = grid_info["cols"]
        col_gap = grid_info["col_gap"]
        return LayoutDecision(
            node_id=node.id,
            strategy=LayoutStrategy.GRID,
            grid_template_columns=f"repeat({cols}, 1fr)",
            gap=_fmt_px(col_gap) if col_gap > 0 else None,
            notes=f"Grid pattern detected: {grid_info['rows']}x{cols}",
        )

    # Rule 6: Check if children are arranged horizontally or vertically
    # by analyzing their positions
    children_sorted_x = sorted(visible_children, key=lambda c: c.bounds.x)
    children_sorted_y = sorted(visible_children, key=lambda c: c.bounds.y)

    # Check horizontal arrangement: children have similar Y but increasing X
    y_values = [c.bounds.y for c in visible_children]
    x_values = [c.bounds.x for c in visible_children]

    y_range = max(y_values) - min(y_values) if y_values else 0
    x_range = max(x_values) - min(x_values) if x_values else 0

    avg_height = sum(c.bounds.height for c in visible_children) / len(visible_children)
    avg_width = sum(c.bounds.width for c in visible_children) / len(visible_children)

    if x_range > y_range and y_range < avg_height * 0.5:
        # Horizontal arrangement
        return LayoutDecision(
            node_id=node.id,
            strategy=LayoutStrategy.FLEX,
            flex_direction="row",
            align_items="center",
            notes="Children arranged horizontally, using flex row",
        )

    if y_range > x_range and x_range < avg_width * 0.5:
        # Vertical arrangement
        return LayoutDecision(
            node_id=node.id,
            strategy=LayoutStrategy.FLEX,
            flex_direction="column",
            notes="Children arranged vertically, using flex column",
        )

    # Default fallback: use flex column (most common web layout)
    return LayoutDecision(
        node_id=node.id,
        strategy=LayoutStrategy.FLEX,
        flex_direction="column",
        notes="Default: flex column layout",
    )


class LayoutStrategyAgent(BaseAgent):
    """Determines the optimal CSS layout strategy for each container node."""

    async def execute(
        self,
        design_spec: DesignSpec,
        use_gpt_fallback: bool = True,
    ) -> LayoutPlan:
        """Analyze the design tree and produce a layout plan.

        Args:
            design_spec: The parsed design specification.
            use_gpt_fallback: Whether to use GPT-4 for ambiguous layouts.

        Returns:
            LayoutPlan mapping each container node to its layout strategy.
        """
        agent_start = time.monotonic()
        logger.info("[job:%s] Layout strategy analysis started", self.job_id)
        await self.report_progress("Starting layout analysis")

        plan = LayoutPlan()
        ambiguous_nodes: list[DesignNode] = []

        # Phase 1: Rules engine
        self._process_node(
            design_spec.root, plan, ambiguous_nodes,
            root_bounds=design_spec.root.bounds,
        )

        await self.report_progress(
            f"Rules engine produced {len(plan.decisions)} decisions, "
            f"{len(ambiguous_nodes)} ambiguous nodes"
        )

        # Phase 2: GPT-4 fallback for ambiguous cases
        if ambiguous_nodes and use_gpt_fallback:
            await self.report_progress("Consulting GPT-4 for ambiguous layouts")
            logger.info("[job:%s] Calling GPT-4 for %d ambiguous nodes", self.job_id, len(ambiguous_nodes))
            try:
                gpt_start = time.monotonic()
                gpt_decisions = await self._gpt_layout_analysis(ambiguous_nodes)
                logger.info("[job:%s] GPT-4 layout response received in %.2fs (%d decisions)",
                             self.job_id, time.monotonic() - gpt_start, len(gpt_decisions))
                for decision in gpt_decisions:
                    plan.set_decision(decision)
            except Exception as e:
                logger.warning("GPT-4 layout fallback failed: %s", e)
                # Use default flex-column for ambiguous nodes
                for node in ambiguous_nodes:
                    plan.set_decision(LayoutDecision(
                        node_id=node.id,
                        strategy=LayoutStrategy.FLEX,
                        flex_direction="column",
                        notes="GPT-4 fallback failed, defaulting to flex column",
                    ))

        logger.info("[job:%s] Layout strategy complete in %.2fs (%d decisions)",
                     self.job_id, time.monotonic() - agent_start, len(plan.decisions))
        await self.report_progress(
            f"Layout analysis complete: {len(plan.decisions)} decisions",
            {"decisions_count": len(plan.decisions)},
        )
        return plan

    def _process_node(
        self,
        node: DesignNode,
        plan: LayoutPlan,
        ambiguous: list[DesignNode],
        root_bounds: Bounds | None = None,
    ) -> None:
        """Recursively process a node and its children."""
        if not node.is_container():
            return

        decision = _analyze_node_layout(node, root_bounds)
        plan.set_decision(decision)

        # Recurse into children (skip out-of-frame nodes)
        for child in node.children:
            if child.visible and _is_within_root(child, root_bounds):
                self._process_node(child, plan, ambiguous, root_bounds)

    async def _gpt_layout_analysis(
        self,
        nodes: list[DesignNode],
    ) -> list[LayoutDecision]:
        """Use GPT-4 to determine layout for ambiguous nodes."""
        prompt_path = PROMPTS_DIR / "layout_strategy.txt"
        system_prompt = prompt_path.read_text(encoding="utf-8")

        nodes_description = []
        for node in nodes:
            child_info = []
            for child in node.children:
                child_info.append({
                    "id": child.id,
                    "name": child.name,
                    "type": child.type,
                    "bounds": {
                        "x": child.bounds.x,
                        "y": child.bounds.y,
                        "width": child.bounds.width,
                        "height": child.bounds.height,
                    },
                })

            nodes_description.append({
                "id": node.id,
                "name": node.name,
                "type": node.type,
                "bounds": {
                    "x": node.bounds.x,
                    "y": node.bounds.y,
                    "width": node.bounds.width,
                    "height": node.bounds.height,
                },
                "children_count": len(node.children),
                "children": child_info,
            })

        user_prompt = (
            "Analyze these container nodes and decide the CSS layout strategy for each:\n\n"
            + json.dumps(nodes_description, indent=2)
            + "\n\nReturn a JSON object mapping node IDs to layout decisions."
        )

        gpt_response = await call_gpt4(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
        )

        return self._parse_gpt_response(gpt_response.content)

    def _parse_gpt_response(self, response: str) -> list[LayoutDecision]:
        """Parse GPT-4's layout analysis response."""
        # Extract JSON from response (may be wrapped in markdown code block)
        json_str = response.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.error("Failed to parse GPT layout response: %s", response[:200])
            return []

        decisions: list[LayoutDecision] = []

        if isinstance(data, dict):
            for node_id, info in data.items():
                if isinstance(info, str):
                    strategy = info
                    extra = {}
                elif isinstance(info, dict):
                    strategy = info.get("strategy", info.get("layout", "flex"))
                    extra = info
                else:
                    continue

                # Normalize strategy name
                strategy = strategy.lower().strip()
                if strategy not in ("flex", "grid", "absolute", "block"):
                    strategy = "flex"

                decisions.append(LayoutDecision(
                    node_id=node_id,
                    strategy=LayoutStrategy(strategy),
                    flex_direction=extra.get("flex_direction"),
                    justify_content=extra.get("justify_content"),
                    align_items=extra.get("align_items"),
                    gap=extra.get("gap"),
                    grid_template_columns=extra.get("grid_template_columns"),
                    grid_template_rows=extra.get("grid_template_rows"),
                    notes=extra.get("notes", "Determined by GPT-4"),
                ))

        return decisions
