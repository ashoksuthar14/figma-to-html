"""Pydantic models for job management."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from schemas.design_spec import DesignSpec, _CamelBase
from schemas.diff_report import DiffReport, DiffRegion, Severity


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


class JobCreate(BaseModel):
    """Request body for creating a new conversion job."""
    design_spec: DesignSpec
    figma_file_key: str = ""
    assets: Optional[list[dict[str, Any]]] = None


class JobResult(_CamelBase):
    """Internal result of a completed conversion job."""
    job_id: str
    status: JobStatus = JobStatus.COMPLETED
    html_content: str = ""
    css_content: str = ""
    verification: Optional[DiffReport] = None
    iterations_used: int = 0
    best_ssim: float = 0.0
    best_mismatch_percent: float = 100.0
    user_modified: bool = False


class JobResponse(_CamelBase):
    """API response for job status queries."""
    job_id: str
    status: JobStatus = JobStatus.QUEUED
    frame_name: str = ""
    result: Optional[JobResult] = None
    error: Optional[str] = None
    progress: int = 0
    current_step: str = ""
    progress_message: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


# ─── Plugin-facing result models ──────────────────────────────────────────────


class PluginDifference(_CamelBase):
    """A single visual difference, mapped from DiffRegion for the plugin."""
    node_id: str = ""
    node_name: str = ""
    issue: str = ""
    severity: str = "low"


class PluginVerificationResult(_CamelBase):
    """Verification scores in the format the Figma plugin expects (0-100)."""
    overall_score: float = 0.0
    layout_score: float = 0.0
    color_score: float = 0.0
    typography_score: float = 0.0
    spacing_score: float = 0.0
    comparison_image_url: Optional[str] = None
    differences: list[PluginDifference] = Field(default_factory=list)

    @classmethod
    def from_diff_report(
        cls, report: DiffReport, base_url: str = "", job_id: str = ""
    ) -> PluginVerificationResult:
        """Convert an internal DiffReport to plugin-facing verification scores."""
        pixel_accuracy = 100.0 - report.pixel_mismatch_percent
        overall = report.ssim_score * 35 + pixel_accuracy * 0.65

        layout_penalty = 0.0
        color_penalty = 0.0
        spacing_penalty = 0.0
        typo_region_penalties: list[float] = []

        _severity_weight = {
            Severity.HIGH: 1.0,
            Severity.MEDIUM: 0.5,
            Severity.LOW: 0.2,
        }

        _TYPO_MULTIPLIER = 4
        _DEFAULT_MULTIPLIER = 6
        _TYPO_REGION_CAP = 20

        for region in report.regions:
            issue_lower = region.issue.lower()
            weight = region.mismatch_percent / 100.0
            sev_mult = _severity_weight.get(region.severity, 0.5)

            if any(kw in issue_lower for kw in ("layout", "position", "size")):
                layout_penalty += weight * _DEFAULT_MULTIPLIER * sev_mult
            elif any(kw in issue_lower for kw in ("color", "background", "fill", "gradient")):
                color_penalty += weight * _DEFAULT_MULTIPLIER * sev_mult
            elif any(kw in issue_lower for kw in ("font", "text", "typography", "letter")):
                typo_region_penalties.append(weight * _TYPO_MULTIPLIER * sev_mult)
            elif any(kw in issue_lower for kw in ("spacing", "padding", "margin", "gap", "align")):
                spacing_penalty += weight * _DEFAULT_MULTIPLIER * sev_mult

        typo_region_penalties.sort(reverse=True)
        typo_penalty = sum(typo_region_penalties[:_TYPO_REGION_CAP])

        layout_penalty = min(layout_penalty, 50.0)
        color_penalty = min(color_penalty, 50.0)
        typo_penalty = min(typo_penalty, 35.0)
        spacing_penalty = min(spacing_penalty, 50.0)

        layout_score = max(0.0, overall - layout_penalty)
        color_score = max(0.0, overall - color_penalty)
        typography_score = max(0.0, overall - typo_penalty)
        spacing_score = max(0.0, overall - spacing_penalty)

        differences = [
            PluginDifference(
                node_id=getattr(region, "node_id", ""),
                node_name=getattr(region, "node_name", ""),
                issue=region.issue,
                severity=region.severity.value,
            )
            for region in report.regions
        ]

        comparison_url = None
        if base_url and job_id and report.diff_image_path:
            comparison_url = f"{base_url}/jobs/{job_id}/diff-image"

        return cls(
            overall_score=round(overall, 1),
            layout_score=round(layout_score, 1),
            color_score=round(color_score, 1),
            typography_score=round(typography_score, 1),
            spacing_score=round(spacing_score, 1),
            comparison_image_url=comparison_url,
            differences=differences,
        )


class PluginJobResult(_CamelBase):
    """Job result in the format the Figma plugin expects (URLs, not inline content)."""
    html_url: str = ""
    css_url: str = ""
    zip_url: str = ""
    preview_url: Optional[str] = None
    verification: Optional[PluginVerificationResult] = None

    @classmethod
    def from_internal(
        cls, result: JobResult, base_url: str, job_id: str
    ) -> PluginJobResult:
        """Convert an internal JobResult to plugin-facing result with URLs."""
        prefix = f"{base_url}/jobs/{job_id}"
        verification = None
        if result.verification:
            verification = PluginVerificationResult.from_diff_report(
                result.verification, base_url, job_id
            )

        return cls(
            html_url=f"{prefix}/html",
            css_url=f"{prefix}/css",
            zip_url=f"{prefix}/download",
            preview_url=f"{prefix}/preview",
            verification=verification,
        )


# ─── Typed WebSocket message models ──────────────────────────────────────────


class WSProgressMessage(_CamelBase):
    """WebSocket progress update message."""
    type: str = "progress"
    job_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = ""
    progress: int = 0
    step: str = ""
    detail: Optional[str] = None


class WSCompletedMessage(_CamelBase):
    """WebSocket job completed message."""
    type: str = "completed"
    job_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result: dict[str, Any] = Field(default_factory=dict)


class WSErrorMessage(_CamelBase):
    """WebSocket error message."""
    type: str = "error"
    job_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: str = ""
    code: Optional[str] = None


class WSLogMessage(_CamelBase):
    """WebSocket log message."""
    type: str = "log"
    job_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    level: str = "info"
    message: str = ""


class WSPingMessage(_CamelBase):
    """WebSocket ping/keepalive message."""
    type: str = "ping"
    job_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─── Micro-fix request/response models ──────────────────────────────────────


class MicroFixRequest(BaseModel):
    """Request body for targeted micro-fix."""
    nodeId: str
    userPrompt: str
    html: str
    css: str


class MicroFixResponse(BaseModel):
    """Response from micro-fix endpoint."""
    html: str
    css: str
    changes_made: bool
    description: str
