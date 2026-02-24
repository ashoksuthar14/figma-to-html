"""Figma REST API service for fetching screenshots and file data."""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

FIGMA_API_BASE = "https://api.figma.com"


def _headers() -> dict[str, str]:
    """Build Figma API request headers."""
    return {
        "X-Figma-Token": settings.FIGMA_ACCESS_TOKEN,
        "Accept": "application/json",
    }


async def get_frame_screenshot(
    file_key: str,
    node_id: str,
    scale: int = 2,
    fmt: str = "png",
) -> bytes:
    """Fetch a rendered screenshot of a Figma frame/node.

    Args:
        file_key: The Figma file key (from the URL).
        node_id: The node ID to render (e.g. "1:23").
        scale: Render scale factor (1-4).
        fmt: Image format ("png", "jpg", "svg", "pdf").

    Returns:
        Raw image bytes.

    Raises:
        RuntimeError: If the Figma API call fails.
    """
    logger.info("Fetching Figma screenshot: file_key=%s, node_id=%s, scale=%d", file_key, node_id, scale)
    # Node IDs in Figma URLs use '-' but the API expects ':'
    api_node_id = node_id.replace("-", ":")

    url = f"{FIGMA_API_BASE}/v1/images/{file_key}"
    params = {
        "ids": api_node_id,
        "format": fmt,
        "scale": str(scale),
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Step 1: Request the rendered image URL from Figma
        response = await client.get(url, headers=_headers(), params=params)

        if response.status_code != 200:
            logger.error(
                "Figma API image request failed: %d %s",
                response.status_code, response.text,
            )
            raise RuntimeError(
                f"Figma API error {response.status_code}: {response.text}"
            )

        data = response.json()
        if data.get("err"):
            raise RuntimeError(f"Figma API error: {data['err']}")

        images = data.get("images", {})
        image_url = images.get(api_node_id)

        if not image_url:
            raise RuntimeError(
                f"No image URL returned for node {api_node_id}. "
                f"Available: {list(images.keys())}"
            )

        # Step 2: Download the actual image
        img_response = await client.get(image_url)

        if img_response.status_code != 200:
            raise RuntimeError(
                f"Failed to download Figma image: {img_response.status_code}"
            )

        logger.info(
            "Fetched Figma screenshot for %s/%s (%d bytes)",
            file_key, node_id, len(img_response.content),
        )
        return img_response.content


async def get_file_nodes(
    file_key: str,
    node_ids: Optional[list[str]] = None,
) -> dict:
    """Fetch node data from the Figma file.

    Args:
        file_key: The Figma file key.
        node_ids: Optional list of specific node IDs to fetch.

    Returns:
        The API response JSON as a dict.
    """
    if node_ids:
        ids_param = ",".join(nid.replace("-", ":") for nid in node_ids)
        url = f"{FIGMA_API_BASE}/v1/files/{file_key}/nodes"
        params = {"ids": ids_param}
    else:
        url = f"{FIGMA_API_BASE}/v1/files/{file_key}"
        params = {}

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, headers=_headers(), params=params)

        if response.status_code != 200:
            raise RuntimeError(
                f"Figma API error {response.status_code}: {response.text}"
            )

        return response.json()
