"""Base agent class for the conversion pipeline."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all pipeline agents.

    Each agent performs a specific step in the Figma-to-HTML conversion.
    Agents can report progress via the job manager's WebSocket system.
    """

    def __init__(self, job_id: str):
        self.job_id = job_id
        self._progress_callback: Optional[Any] = None

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """Execute the agent's primary task.

        Subclasses must implement this with their specific logic.
        """
        pass

    def set_progress_callback(self, callback) -> None:
        """Set the callback function for progress reporting.

        The callback should accept (job_id, message, data) arguments.
        """
        self._progress_callback = callback

    async def report_progress(self, message: str, data: Optional[dict] = None) -> None:
        """Report progress to connected WebSocket clients.

        Args:
            message: Human-readable progress message.
            data: Optional structured data to include.
        """
        logger.info("[Job %s] %s: %s", self.job_id, self.__class__.__name__, message)
        if self._progress_callback:
            try:
                await self._progress_callback(
                    self.job_id,
                    message,
                    data or {},
                )
            except Exception as e:
                logger.warning("Failed to send progress update: %s", e)
