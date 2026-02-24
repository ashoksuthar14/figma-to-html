"""SQLite persistence layer for job metadata and content."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiosqlite

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).parent / "data"
DB_PATH = DB_DIR / "jobs.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id              TEXT PRIMARY KEY,
    status              TEXT NOT NULL DEFAULT 'queued',
    frame_name          TEXT NOT NULL DEFAULT '',
    figma_file_key      TEXT NOT NULL DEFAULT '',
    html_content        TEXT NOT NULL DEFAULT '',
    css_content         TEXT NOT NULL DEFAULT '',
    progress            INTEGER NOT NULL DEFAULT 0,
    current_step        TEXT NOT NULL DEFAULT '',
    error               TEXT,
    best_ssim           REAL NOT NULL DEFAULT 0,
    best_mismatch_pct   REAL NOT NULL DEFAULT 100,
    iterations_used     INTEGER NOT NULL DEFAULT 0,
    user_modified       INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    completed_at        TEXT
);
"""


async def _connect() -> aiosqlite.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(DB_PATH))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL;")
    return conn


async def init_db() -> None:
    """Create the jobs table if it does not exist."""
    conn = await _connect()
    try:
        await conn.execute(_CREATE_TABLE)
        await conn.commit()
        logger.info("SQLite database initialised at %s", DB_PATH)
    finally:
        await conn.close()


async def save_job(
    job_id: str,
    *,
    status: str = "queued",
    frame_name: str = "",
    figma_file_key: str = "",
    html_content: str = "",
    css_content: str = "",
    progress: int = 0,
    current_step: str = "",
    error: Optional[str] = None,
    best_ssim: float = 0.0,
    best_mismatch_pct: float = 100.0,
    iterations_used: int = 0,
    user_modified: bool = False,
    created_at: Optional[str] = None,
    updated_at: Optional[str] = None,
    completed_at: Optional[str] = None,
) -> None:
    """Insert or replace a job row (full upsert)."""
    now = datetime.now(timezone.utc).isoformat()
    conn = await _connect()
    try:
        await conn.execute(
            """
            INSERT INTO jobs (
                job_id, status, frame_name, figma_file_key,
                html_content, css_content,
                progress, current_step, error,
                best_ssim, best_mismatch_pct, iterations_used, user_modified,
                created_at, updated_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                status          = excluded.status,
                frame_name      = excluded.frame_name,
                figma_file_key  = excluded.figma_file_key,
                html_content    = excluded.html_content,
                css_content     = excluded.css_content,
                progress        = excluded.progress,
                current_step    = excluded.current_step,
                error           = excluded.error,
                best_ssim       = excluded.best_ssim,
                best_mismatch_pct = excluded.best_mismatch_pct,
                iterations_used = excluded.iterations_used,
                user_modified   = excluded.user_modified,
                updated_at      = excluded.updated_at,
                completed_at    = excluded.completed_at
            """,
            (
                job_id,
                status,
                frame_name,
                figma_file_key,
                html_content,
                css_content,
                progress,
                current_step,
                error,
                best_ssim,
                best_mismatch_pct,
                iterations_used,
                1 if user_modified else 0,
                created_at or now,
                updated_at or now,
                completed_at,
            ),
        )
        await conn.commit()
    finally:
        await conn.close()


async def update_job_status(
    job_id: str,
    *,
    status: str,
    progress: int = 0,
    current_step: str = "",
) -> None:
    """Lightweight update for status/progress changes (no content rewrite)."""
    now = datetime.now(timezone.utc).isoformat()
    conn = await _connect()
    try:
        await conn.execute(
            """
            UPDATE jobs
               SET status = ?, progress = ?, current_step = ?, updated_at = ?
             WHERE job_id = ?
            """,
            (status, progress, current_step, now, job_id),
        )
        await conn.commit()
    finally:
        await conn.close()


async def update_job_error(job_id: str, error: str) -> None:
    """Record a failure."""
    now = datetime.now(timezone.utc).isoformat()
    conn = await _connect()
    try:
        await conn.execute(
            """
            UPDATE jobs
               SET status = 'failed', error = ?, updated_at = ?
             WHERE job_id = ?
            """,
            (error, now, job_id),
        )
        await conn.commit()
    finally:
        await conn.close()


async def update_job_result(
    job_id: str,
    *,
    html_content: str,
    css_content: str,
    best_ssim: float = 0.0,
    best_mismatch_pct: float = 100.0,
    iterations_used: int = 0,
) -> None:
    """Persist the completed result content and scores."""
    now = datetime.now(timezone.utc).isoformat()
    conn = await _connect()
    try:
        await conn.execute(
            """
            UPDATE jobs
               SET status = 'completed',
                   html_content = ?,
                   css_content = ?,
                   best_ssim = ?,
                   best_mismatch_pct = ?,
                   iterations_used = ?,
                   progress = 100,
                   current_step = 'Conversion complete',
                   updated_at = ?,
                   completed_at = ?
             WHERE job_id = ?
            """,
            (
                html_content,
                css_content,
                best_ssim,
                best_mismatch_pct,
                iterations_used,
                now,
                now,
                job_id,
            ),
        )
        await conn.commit()
    finally:
        await conn.close()


async def update_job_content(
    job_id: str,
    *,
    html_content: str,
    css_content: str,
) -> None:
    """Persist user-edited HTML/CSS."""
    now = datetime.now(timezone.utc).isoformat()
    conn = await _connect()
    try:
        await conn.execute(
            """
            UPDATE jobs
               SET html_content = ?, css_content = ?, user_modified = 1, updated_at = ?
             WHERE job_id = ?
            """,
            (html_content, css_content, now, job_id),
        )
        await conn.commit()
    finally:
        await conn.close()


async def load_all_jobs() -> list[dict[str, Any]]:
    """Return every job row as a dict, newest first."""
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def load_job(job_id: str) -> Optional[dict[str, Any]]:
    """Return a single job row or None."""
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await conn.close()


async def delete_job(job_id: str) -> None:
    """Delete a job row."""
    conn = await _connect()
    try:
        await conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        await conn.commit()
    finally:
        await conn.close()
