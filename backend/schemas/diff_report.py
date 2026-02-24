"""Pydantic models for the visual verification diff report."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DiffRegion(BaseModel):
    """A region of visual mismatch between expected and actual rendering."""
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    area: float = Field(0.0, description="Area of the mismatch region in pixels")
    issue: str = Field("", description="Description of the mismatch")
    severity: Severity = Severity.LOW
    mismatch_percent: float = Field(
        0.0, ge=0.0, le=100.0,
        description="Percentage of pixels mismatched in this region",
    )


class DiffReport(BaseModel):
    """Complete report from visual verification comparison."""
    passed: bool = False
    pixel_mismatch_percent: float = Field(
        0.0, ge=0.0, le=100.0,
        description="Overall percentage of pixels that differ",
    )
    ssim_score: float = Field(
        0.0, ge=0.0, le=1.0,
        description="Structural similarity index (1.0 = identical)",
    )
    diff_image_path: Optional[str] = Field(
        None, description="Path to the generated diff heatmap image"
    )
    regions: list[DiffRegion] = Field(
        default_factory=list,
        description="List of identified mismatch regions",
    )
    figma_screenshot_path: Optional[str] = None
    rendered_screenshot_path: Optional[str] = None
    total_pixels: int = 0
    mismatched_pixels: int = 0

    @property
    def high_severity_regions(self) -> list[DiffRegion]:
        """Get only high-severity mismatch regions."""
        return [r for r in self.regions if r.severity == Severity.HIGH]

    @property
    def summary(self) -> str:
        """Human-readable summary of the diff report."""
        status = "PASSED" if self.passed else "FAILED"
        return (
            f"Verification {status}: "
            f"pixel mismatch {self.pixel_mismatch_percent:.2f}%, "
            f"SSIM {self.ssim_score:.4f}, "
            f"{len(self.regions)} mismatch region(s)"
        )
