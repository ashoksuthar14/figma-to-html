"""Pydantic models for the layout strategy output."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class LayoutStrategy(str, Enum):
    FLEX = "flex"
    GRID = "grid"
    ABSOLUTE = "absolute"
    BLOCK = "block"


class LayoutDecision(BaseModel):
    """Layout decision for a single container node."""
    node_id: str
    strategy: LayoutStrategy
    flex_direction: Optional[str] = Field(
        None, description="row or column, only for flex strategy"
    )
    justify_content: Optional[str] = Field(
        None, description="CSS justify-content value"
    )
    align_items: Optional[str] = Field(
        None, description="CSS align-items value"
    )
    flex_wrap: Optional[str] = Field(
        None, description="CSS flex-wrap value"
    )
    gap: Optional[str] = Field(
        None, description="CSS gap value"
    )
    grid_template_columns: Optional[str] = Field(
        None, description="CSS grid-template-columns, only for grid strategy"
    )
    grid_template_rows: Optional[str] = Field(
        None, description="CSS grid-template-rows, only for grid strategy"
    )
    notes: Optional[str] = Field(
        None, description="Reasoning notes for this decision"
    )


class LayoutPlan(BaseModel):
    """Complete layout plan mapping node IDs to layout decisions."""
    decisions: dict[str, LayoutDecision] = Field(
        default_factory=dict,
        description="Mapping of node_id to LayoutDecision",
    )

    def get_decision(self, node_id: str) -> Optional[LayoutDecision]:
        """Get the layout decision for a specific node."""
        return self.decisions.get(node_id)

    def set_decision(self, decision: LayoutDecision) -> None:
        """Set or update a layout decision."""
        self.decisions[decision.node_id] = decision
