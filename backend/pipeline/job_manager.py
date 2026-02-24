"""Job manager: in-memory job storage backed by SQLite, plus WebSocket registry."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import WebSocket

import db as _db
from schemas.design_spec import DesignSpec
from schemas.job import (
    JobResponse,
    JobResult,
    JobStatus,
    PluginJobResult,
    WSCompletedMessage,
    WSErrorMessage,
    WSLogMessage,
    WSProgressMessage,
)

logger = logging.getLogger(__name__)


class JobManager:
    """Manages conversion jobs and WebSocket connections.

    In-memory dicts are the primary read path for speed; SQLite is the
    persistence layer so jobs survive server restarts.
    """

    def __init__(self):
        self._jobs: dict[str, JobResponse] = {}
        self._results: dict[str, JobResult] = {}
        self._design_specs: dict[str, DesignSpec] = {}
        self._ws_connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    # -- Initialisation (called once at startup) --

    async def init(self) -> None:
        """Initialise the SQLite database and hydrate in-memory dicts."""
        await _db.init_db()

        rows = await _db.load_all_jobs()
        for row in rows:
            job_id = row["job_id"]
            status = JobStatus(row["status"])
            created_at = datetime.fromisoformat(row["created_at"])
            updated_at = datetime.fromisoformat(row["updated_at"])
            completed_at = (
                datetime.fromisoformat(row["completed_at"])
                if row["completed_at"]
                else None
            )

            job = JobResponse(
                job_id=job_id,
                status=status,
                frame_name=row.get("frame_name", ""),
                progress=row["progress"],
                current_step=row["current_step"],
                error=row.get("error"),
                created_at=created_at,
                updated_at=updated_at,
                completed_at=completed_at,
            )

            if status == JobStatus.COMPLETED and row["html_content"]:
                result = JobResult(
                    job_id=job_id,
                    status=JobStatus.COMPLETED,
                    html_content=row["html_content"],
                    css_content=row["css_content"],
                    best_ssim=row.get("best_ssim", 0.0),
                    best_mismatch_percent=row.get("best_mismatch_pct", 100.0),
                    iterations_used=row.get("iterations_used", 0),
                    user_modified=bool(row.get("user_modified", 0)),
                )
                self._results[job_id] = result
                job.result = result

            # Jobs that were mid-processing when the server stopped are stale;
            # mark them as failed so the user sees a clear state.
            if status in (JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.VERIFYING):
                job.status = JobStatus.FAILED
                job.error = "Server restarted while job was in progress"
                await _db.update_job_error(job_id, job.error)

            self._jobs[job_id] = job

        logger.info("Hydrated %d jobs from SQLite", len(rows))

    # -- Job lifecycle --

    async def create_job(
        self, design_spec: DesignSpec, *, frame_name: str = ""
    ) -> str:
        """Create a new conversion job and persist it to SQLite.

        Args:
            design_spec: The Figma design specification to convert.
            frame_name: Human-readable name for the job (from Figma metadata).

        Returns:
            The generated job ID (UUID4).
        """
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        self._jobs[job_id] = JobResponse(
            job_id=job_id,
            status=JobStatus.QUEUED,
            frame_name=frame_name,
            created_at=now,
            updated_at=now,
        )
        self._design_specs[job_id] = design_spec

        await _db.save_job(
            job_id,
            status="queued",
            frame_name=frame_name,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )

        logger.info("Created job %s (%s)", job_id, frame_name or "unnamed")
        return job_id

    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        message: str = "",
        progress: int = 0,
        step: str = "",
    ) -> None:
        """Update a job's status and notify WebSocket clients.

        Args:
            job_id: The job identifier.
            status: New job status.
            message: Human-readable progress message.
            progress: Progress percentage (0-100).
            step: Current step description.
        """
        if job_id not in self._jobs:
            logger.warning("Attempted to update unknown job %s", job_id)
            return

        self._jobs[job_id].status = status
        self._jobs[job_id].progress = progress
        self._jobs[job_id].current_step = step or message
        self._jobs[job_id].progress_message = message
        self._jobs[job_id].updated_at = datetime.now(timezone.utc)

        await _db.update_job_status(
            job_id,
            status=status.value,
            progress=progress,
            current_step=step or message,
        )

        await self.broadcast(job_id, WSProgressMessage(
            job_id=job_id,
            status=status.value,
            progress=progress,
            step=step or message,
            detail=message,
        ))

    async def set_result(
        self, job_id: str, result: JobResult, base_url: str = ""
    ) -> None:
        """Store the final result for a completed job.

        Args:
            job_id: The job identifier.
            result: The conversion result.
            base_url: Base URL for constructing download URLs.
        """
        self._results[job_id] = result
        logger.info("Result stored for job %s", job_id)

        now = datetime.now(timezone.utc)
        if job_id in self._jobs:
            self._jobs[job_id].result = result
            self._jobs[job_id].status = JobStatus.COMPLETED
            self._jobs[job_id].progress = 100
            self._jobs[job_id].current_step = "Conversion complete"
            self._jobs[job_id].updated_at = now
            self._jobs[job_id].completed_at = now

        await _db.update_job_result(
            job_id,
            html_content=result.html_content,
            css_content=result.css_content,
            best_ssim=result.best_ssim,
            best_mismatch_pct=result.best_mismatch_percent,
            iterations_used=result.iterations_used,
        )

        # Build plugin-facing result for the WS message
        plugin_result = PluginJobResult.from_internal(result, base_url, job_id)

        await self.broadcast(job_id, WSCompletedMessage(
            job_id=job_id,
            result=plugin_result.model_dump(by_alias=True),
        ))

    async def set_error(self, job_id: str, error: str) -> None:
        """Record an error for a failed job.

        Args:
            job_id: The job identifier.
            error: Error message.
        """
        logger.error("Job %s failed: %s", job_id, error)
        if job_id in self._jobs:
            self._jobs[job_id].status = JobStatus.FAILED
            self._jobs[job_id].error = error
            self._jobs[job_id].updated_at = datetime.now(timezone.utc)

        await _db.update_job_error(job_id, error)

        await self.broadcast(job_id, WSErrorMessage(
            job_id=job_id,
            error=error,
        ))

    async def persist_content_update(
        self, job_id: str, html: str, css: str
    ) -> None:
        """Persist a user-initiated HTML/CSS edit to SQLite."""
        await _db.update_job_content(job_id, html_content=html, css_content=css)

    def get_job(self, job_id: str) -> Optional[JobResponse]:
        """Retrieve job status and results.

        Args:
            job_id: The job identifier.

        Returns:
            JobResponse or None if job not found.
        """
        return self._jobs.get(job_id)

    def get_design_spec(self, job_id: str) -> Optional[DesignSpec]:
        """Retrieve the design spec for a job.

        Args:
            job_id: The job identifier.

        Returns:
            DesignSpec or None if not found.
        """
        return self._design_specs.get(job_id)

    def get_result(self, job_id: str) -> Optional[JobResult]:
        """Retrieve the result for a completed job.

        Args:
            job_id: The job identifier.

        Returns:
            JobResult or None if not found.
        """
        return self._results.get(job_id)

    # -- WebSocket connection management --

    async def register_ws(self, job_id: str, ws: WebSocket) -> None:
        """Register a WebSocket connection for job updates.

        Args:
            job_id: The job to subscribe to.
            ws: The WebSocket connection.
        """
        async with self._lock:
            if job_id not in self._ws_connections:
                self._ws_connections[job_id] = []
            self._ws_connections[job_id].append(ws)
            logger.info("WebSocket registered for job %s (total: %d)",
                        job_id, len(self._ws_connections[job_id]))

    async def unregister_ws(self, job_id: str, ws: WebSocket) -> None:
        """Unregister a WebSocket connection.

        Args:
            job_id: The job ID.
            ws: The WebSocket connection to remove.
        """
        async with self._lock:
            if job_id in self._ws_connections:
                try:
                    self._ws_connections[job_id].remove(ws)
                except ValueError:
                    logger.debug("WebSocket not found in list for job %s during unregister", job_id)
                if not self._ws_connections[job_id]:
                    del self._ws_connections[job_id]
                logger.info("WebSocket unregistered for job %s", job_id)

    async def broadcast(self, job_id: str, message) -> None:
        """Send a message to all WebSocket connections for a job.

        Args:
            job_id: The job ID.
            message: A typed WS message model (_CamelBase subclass).
        """
        connections = self._ws_connections.get(job_id, [])
        if not connections:
            return

        payload = message.model_dump_json(by_alias=True)
        dead_connections: list[WebSocket] = []

        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception as e:
                logger.debug("WebSocket send failed: %s", e)
                dead_connections.append(ws)

        # Clean up dead connections
        for ws in dead_connections:
            await self.unregister_ws(job_id, ws)

    async def send_progress(
        self,
        job_id: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Convenience method to send a log-level progress update via WebSocket.

        This is the callback used by agents via report_progress().

        Args:
            job_id: The job identifier.
            message: Progress message.
            data: Optional structured data (ignored, kept for API compat).
        """
        ws_msg = WSLogMessage(
            job_id=job_id,
            level="info",
            message=message,
        )
        await self.broadcast(job_id, ws_msg)

    async def delete_job(self, job_id: str) -> bool:
        """Delete a job from memory and database. Returns True if found."""
        found = job_id in self._jobs
        self._jobs.pop(job_id, None)
        self._results.pop(job_id, None)
        self._design_specs.pop(job_id, None)
        async with self._lock:
            self._ws_connections.pop(job_id, None)
        await _db.delete_job(job_id)
        return found

    def list_jobs(self, limit: int = 50) -> list[JobResponse]:
        """List recent jobs.

        Args:
            limit: Maximum number of jobs to return.

        Returns:
            List of JobResponse objects, newest first.
        """
        jobs = sorted(
            self._jobs.values(),
            key=lambda j: j.created_at,
            reverse=True,
        )
        return jobs[:limit]


# Global singleton instance
job_manager = JobManager()
