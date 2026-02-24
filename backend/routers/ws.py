"""WebSocket router for real-time job progress updates."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pipeline.job_manager import job_manager
from schemas.job import WSLogMessage, WSPingMessage, WSProgressMessage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str) -> None:
    """WebSocket endpoint for receiving real-time progress updates for a job.

    Protocol:
    - Client connects to /ws/{job_id}
    - Server sends typed JSON messages with a "type" field
    - Message types: progress, completed, error, log, ping
    - Connection stays open until job completes/fails or client disconnects
    """
    # Verify the job exists
    job = job_manager.get_job(job_id)
    if job is None:
        await websocket.close(code=4004, reason=f"Job {job_id} not found")
        return

    await websocket.accept()
    logger.info("WebSocket connected for job %s", job_id)

    # Register this connection
    await job_manager.register_ws(job_id, websocket)

    # Send current job status immediately
    try:
        msg = WSProgressMessage(
            job_id=job_id,
            status=job.status.value,
            progress=job.progress,
            step=job.current_step or f"Connected. Current status: {job.status.value}",
            detail=job.progress_message or None,
        )
        await websocket.send_text(msg.model_dump_json(by_alias=True))
    except Exception as e:
        logger.warning("Failed to send initial status: %s", e)

    # Keep connection alive and handle incoming messages
    try:
        while True:
            # Wait for client messages (ping/pong, or explicit close)
            data = await websocket.receive_text()

            # Handle client commands
            try:
                parsed = json.loads(data)
                command = parsed.get("command", "")

                if command == "ping":
                    msg = WSPingMessage(job_id=job_id)
                    await websocket.send_text(msg.model_dump_json(by_alias=True))
                elif command == "status":
                    current_job = job_manager.get_job(job_id)
                    if current_job:
                        msg = WSProgressMessage(
                            job_id=job_id,
                            status=current_job.status.value,
                            progress=current_job.progress,
                            step=current_job.current_step,
                            detail=current_job.error or current_job.progress_message or None,
                        )
                        await websocket.send_text(msg.model_dump_json(by_alias=True))
            except json.JSONDecodeError:
                # Not JSON, treat as echo/log
                msg = WSLogMessage(
                    job_id=job_id,
                    level="info",
                    message=data,
                )
                await websocket.send_text(msg.model_dump_json(by_alias=True))

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for job %s", job_id)
    except Exception as e:
        logger.warning("WebSocket error for job %s: %s", job_id, e)
    finally:
        await job_manager.unregister_ws(job_id, websocket)
