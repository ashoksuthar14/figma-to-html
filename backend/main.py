"""FastAPI application entry point for the Figma-to-HTML converter backend."""

from __future__ import annotations

import logging
import logging.handlers
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import jobs, ws


def setup_logging() -> None:
    """Configure logging from settings (LOG_LEVEL, LOG_FILE)."""
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    if not root.handlers:
        console = logging.StreamHandler()
        console.setLevel(level)
        console.setFormatter(fmt)
        root.addHandler(console)

    # Optional rotating file handler
    if settings.LOG_FILE:
        log_path = Path(settings.LOG_FILE)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)


setup_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown events."""
    # Startup
    logger.info("Starting Figma-to-HTML backend (log_level=%s, log_file=%s)",
                settings.LOG_LEVEL, settings.LOG_FILE or "console only")
    settings.ensure_dirs()
    logger.info("Output directory: %s", settings.OUTPUT_DIR)
    logger.info("Temp directory: %s", settings.TEMP_DIR)

    from pipeline.job_manager import job_manager
    await job_manager.init()

    yield
    # Shutdown
    logger.info("Shutting down Figma-to-HTML backend")
    try:
        from services.browser_service import close_browser
        await close_browser()
    except Exception as e:
        logger.warning("Error closing browser: %s", e)


app = FastAPI(
    title="Figma-to-HTML Converter",
    description="AI-powered pipeline that converts Figma designs to pixel-perfect HTML/CSS",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware - allow all origins for the Figma plugin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(jobs.router)
app.include_router(ws.router)


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """Health check endpoint.

    Returns:
        Dict with status and configuration info.
    """
    return {
        "status": "healthy",
        "version": "0.1.0",
        "openai_configured": bool(settings.OPENAI_API_KEY),
        "figma_configured": bool(settings.FIGMA_ACCESS_TOKEN),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=True,
        reload_dirs=["."],
        log_config=None,
        log_level=settings.LOG_LEVEL.lower(),
    )
