"""Jobs API router: create, query, and download conversion jobs."""

from __future__ import annotations

import asyncio
import base64
import io
import json as json_module
import logging
import shutil
import zipfile
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse

from config import settings
from pipeline.job_manager import job_manager
from pipeline.orchestrator import run_pipeline
from schemas.design_spec import DesignSpec
from schemas.job import JobCreate, JobResponse, JobStatus, MicroFixRequest, PluginJobResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _get_base_url(request: Request) -> str:
    """Derive the base URL from the incoming request."""
    return str(request.base_url).rstrip("/")


def _to_api_response(job: JobResponse, base_url: str) -> dict:
    """Transform an internal JobResponse to the plugin-expected JSON format."""
    data = {
        "jobId": job.job_id,
        "status": job.status.value,
        "frameName": job.frame_name,
        "progress": job.progress,
        "currentStep": job.current_step,
        "createdAt": job.created_at.isoformat(),
        "updatedAt": job.updated_at.isoformat(),
        "completedAt": job.completed_at.isoformat() if job.completed_at else None,
        "error": job.error,
        "result": None,
    }

    if job.status == JobStatus.COMPLETED and job.result:
        plugin_result = PluginJobResult.from_internal(job.result, base_url, job.job_id)
        data["result"] = plugin_result.model_dump(by_alias=True)

    return data


@router.post("", status_code=201)
async def create_job(
    request: Request,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """Create a new Figma-to-HTML conversion job.

    Accepts the design spec as either:
    - JSON body (application/json) with design_spec or designSpec
    - Multipart form with 'design_spec_json' field and optional file uploads

    Returns the job ID and initial status. The pipeline runs in the background.
    """
    design_spec: Optional[DesignSpec] = None
    files: list[UploadFile] = []
    content_type = request.headers.get("content-type", "")
    logger.info("POST /jobs received (content-type: %s)", content_type)

    if "application/json" in content_type:
        # JSON body from the plugin
        try:
            body = await request.json()
        except Exception as e:
            logger.warning("Invalid JSON body: %s", e)
            raise HTTPException(status_code=422, detail=f"Invalid JSON body: {e}")

        # Accept both camelCase (designSpec) and snake_case (design_spec)
        spec_data = body.get("design_spec") or body.get("designSpec")
        if spec_data is None:
            logger.warning("JSON body missing 'design_spec' or 'designSpec' key")
            raise HTTPException(
                status_code=422,
                detail="JSON body must contain 'design_spec' or 'designSpec'",
            )
        try:
            design_spec = DesignSpec.model_validate(spec_data)
        except Exception as e:
            logger.warning("Invalid design spec: %s", e)
            raise HTTPException(status_code=422, detail=f"Invalid design spec: {e}")

    elif "multipart/form-data" in content_type:
        # Form data with optional file uploads
        form = await request.form()
        design_spec_json = form.get("design_spec_json")
        if design_spec_json is None:
            logger.warning("Multipart form missing 'design_spec_json' field")
            raise HTTPException(
                status_code=422,
                detail="Multipart form must contain 'design_spec_json' field",
            )
        try:
            spec_dict = json_module.loads(design_spec_json)
            design_spec = DesignSpec.model_validate(spec_dict)
        except Exception as e:
            logger.warning("Invalid design spec JSON in multipart form: %s", e)
            raise HTTPException(
                status_code=422,
                detail=f"Invalid design spec JSON: {e}",
            )
        # Collect uploaded files
        for key in form:
            value = form[key]
            if isinstance(value, UploadFile):
                files.append(value)

    else:
        logger.warning("Unsupported content-type: %s", content_type)
        raise HTTPException(
            status_code=422,
            detail="Expected Content-Type: application/json or multipart/form-data",
        )

    frame_name = design_spec.metadata.frame_name if design_spec.metadata else "unknown"
    node_count = 1 + len(design_spec.root.get_all_descendants()) if design_spec.root else 0
    has_screenshot = design_spec.frame_screenshot is not None
    screenshot_len = len(design_spec.frame_screenshot) if has_screenshot else 0
    logger.info(
        "Design spec parsed: frame=%s, nodes=%d, has_screenshot=%s (len=%d)",
        frame_name, node_count, has_screenshot, screenshot_len,
    )

    # Create the job
    frame_name = ""
    if design_spec.metadata:
        frame_name = design_spec.metadata.frame_name or ""
    job_id = await job_manager.create_job(design_spec, frame_name=frame_name)

    # Handle uploaded asset files
    if files:
        asset_dir = Path(settings.TEMP_DIR) / job_id / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        for upload_file in files:
            if upload_file.filename:
                file_path = asset_dir / upload_file.filename
                content = await upload_file.read()
                file_path.write_bytes(content)
                logger.info(
                    "Saved asset %s for job %s (%d bytes)",
                    upload_file.filename, job_id, len(content),
                )

    # Save base64-encoded assets from the design spec
    if design_spec.assets:
        asset_dir = Path(settings.TEMP_DIR) / job_id / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        for asset in design_spec.assets:
            if asset.data_base64:
                try:
                    data = base64.b64decode(asset.data_base64)
                    file_path = asset_dir / asset.filename
                    file_path.write_bytes(data)
                    # Set relative URL so output works both standalone and via API
                    asset.url = f"assets/{asset.filename}"
                    logger.info(
                        "Saved base64 asset %s for job %s (%d bytes)",
                        asset.filename, job_id, len(data),
                    )
                except Exception as e:
                    logger.warning("Failed to decode base64 asset %s: %s", asset.filename, e)

    # Decode and save frame screenshot from the plugin (for visual verification)
    figma_screenshot_bytes: Optional[bytes] = None
    if design_spec.frame_screenshot:
        try:
            figma_screenshot_bytes = base64.b64decode(design_spec.frame_screenshot)
            screenshot_dir = Path(settings.TEMP_DIR) / job_id
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = screenshot_dir / "figma_screenshot.png"
            screenshot_path.write_bytes(figma_screenshot_bytes)
            logger.info(
                "Saved frame screenshot for job %s (%d bytes)",
                job_id, len(figma_screenshot_bytes),
            )
        except Exception as e:
            logger.warning("Failed to decode frame screenshot: %s", e)
            figma_screenshot_bytes = None

    # Save design spec JSON for debugging
    try:
        spec_debug_dir = Path(settings.TEMP_DIR) / job_id
        spec_debug_dir.mkdir(parents=True, exist_ok=True)
        spec_json_path = spec_debug_dir / "design_spec.json"
        spec_json_path.write_text(
            design_spec.model_dump_json(indent=2, by_alias=True),
            encoding="utf-8",
        )
        logger.info("Saved design spec JSON for job %s", job_id)
    except Exception as e:
        logger.warning("Failed to save design spec JSON: %s", e)

    logger.info("Job %s created, starting pipeline", job_id)

    base_url = _get_base_url(request)

    # Start the pipeline in the background
    background_tasks.add_task(
        run_pipeline, job_id, design_spec, base_url,
        figma_screenshot=figma_screenshot_bytes,
    )

    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=500, detail="Failed to create job")

    # Build WebSocket URL
    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{request.url.netloc}/ws/{job_id}"

    return JSONResponse(
        status_code=201,
        content={
            "jobId": job.job_id,
            "status": job.status.value,
            "createdAt": job.created_at.isoformat(),
            "wsUrl": ws_url,
        },
    )


@router.get("")
async def list_jobs(request: Request, limit: int = 50) -> JSONResponse:
    """List recent conversion jobs."""
    base_url = _get_base_url(request)
    jobs = job_manager.list_jobs(limit=limit)
    return JSONResponse(content=[_to_api_response(j, base_url) for j in jobs])


@router.get("/{job_id}")
async def get_job(job_id: str, request: Request) -> JSONResponse:
    """Get the current status and results of a conversion job."""
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    base_url = _get_base_url(request)
    return JSONResponse(content=_to_api_response(job, base_url))


@router.delete("/{job_id}")
async def delete_job(job_id: str) -> JSONResponse:
    """Delete a job and its output files."""
    found = await job_manager.delete_job(job_id)
    if not found:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    output_dir = Path(settings.OUTPUT_DIR) / job_id
    temp_dir = Path(settings.TEMP_DIR) / job_id
    shutil.rmtree(output_dir, ignore_errors=True)
    shutil.rmtree(temp_dir, ignore_errors=True)

    logger.info("Deleted job %s", job_id)
    return JSONResponse(content={"deleted": True, "jobId": job_id})


@router.get("/{job_id}/styles.css")
async def get_styles_css(job_id: str) -> Response:
    """Serve the generated CSS as styles.css (so the HTML <link> tag works)."""
    return await get_css(job_id)


@router.get("/{job_id}/assets/{filename:path}")
async def get_asset(job_id: str, filename: str) -> Response:
    """Serve uploaded asset files (images, fonts, etc.) for a job."""
    asset_path = Path(settings.TEMP_DIR) / job_id / "assets" / filename
    if not asset_path.exists():
        # Also check output directory
        asset_path = Path(settings.OUTPUT_DIR) / job_id / "assets" / filename
    if not asset_path.exists():
        raise HTTPException(status_code=404, detail=f"Asset '{filename}' not found")

    content = asset_path.read_bytes()

    # Detect actual content type from file content first (SVGs may have .png extension)
    if content[:4] == b"<svg" or content[:5] == b"<?xml":
        media_type = "image/svg+xml"
    else:
        suffix = asset_path.suffix.lower()
        media_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".webp": "image/webp",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
            ".ttf": "font/ttf",
            ".otf": "font/otf",
        }
        media_type = media_types.get(suffix, "application/octet-stream")

    return Response(content=content, media_type=media_type)


@router.get("/{job_id}/html")
async def get_html(job_id: str) -> Response:
    """Serve the generated HTML file."""
    result = job_manager.get_result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No result for job {job_id}")

    # Try file on disk first, fall back to in-memory content
    html_path = Path(settings.OUTPUT_DIR) / job_id / "index.html"
    if html_path.exists():
        content = html_path.read_text(encoding="utf-8")
    else:
        content = result.html_content

    return Response(content=content, media_type="text/html")


@router.get("/{job_id}/css")
async def get_css(job_id: str) -> Response:
    """Serve the generated CSS file."""
    result = job_manager.get_result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No result for job {job_id}")

    css_path = Path(settings.OUTPUT_DIR) / job_id / "styles.css"
    if css_path.exists():
        content = css_path.read_text(encoding="utf-8")
    else:
        content = result.css_content

    # Rewrite relative asset paths so preview and linked CSS resolve correctly
    assets_prefix = f"/jobs/{job_id}/assets/"
    content = content.replace("url('assets/", f"url('{assets_prefix}")
    content = content.replace('url("assets/', f'url("{assets_prefix}')

    return Response(content=content, media_type="text/css")


@router.get("/{job_id}/preview")
async def get_preview(job_id: str) -> Response:
    """Serve a full preview HTML page with inline CSS."""
    result = job_manager.get_result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No result for job {job_id}")

    # Try to read from disk for the full rendered page
    html_path = Path(settings.OUTPUT_DIR) / job_id / "index.html"
    if html_path.exists():
        content = html_path.read_text(encoding="utf-8")
    else:
        content = result.html_content

    # Rewrite relative asset paths to absolute URLs so they resolve correctly
    assets_prefix = f"/jobs/{job_id}/assets/"
    content = content.replace('src="assets/', f'src="{assets_prefix}')
    content = content.replace("src='assets/", f"src='{assets_prefix}")
    content = content.replace("url('assets/", f"url('{assets_prefix}")
    content = content.replace('url("assets/', f'url("{assets_prefix}')

    return Response(content=content, media_type="text/html")


@router.get("/{job_id}/diff-image")
async def get_diff_image(job_id: str) -> Response:
    """Serve the diff heatmap image from verification."""
    result = job_manager.get_result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No result for job {job_id}")

    if not result.verification or not result.verification.diff_image_path:
        raise HTTPException(status_code=404, detail="No diff image available")

    diff_path = Path(result.verification.diff_image_path)
    if not diff_path.exists():
        raise HTTPException(status_code=404, detail="Diff image file not found")

    return Response(content=diff_path.read_bytes(), media_type="image/png")


@router.post("/{job_id}/update")
async def update_job(job_id: str, request: Request) -> JSONResponse:
    """Accept partial edits to a completed job's HTML/CSS.

    Body: { "html": str, "css": str }
    Persists to disk and updates the in-memory result.
    """
    result = job_manager.get_result(job_id)
    if result is None:
        job = job_manager.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        raise HTTPException(
            status_code=400,
            detail=f"Job {job_id} has no results yet (status: {job.status.value})",
        )

    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid JSON body: {e}")

    new_html = body.get("html")
    new_css = body.get("css")

    if new_html is None and new_css is None:
        raise HTTPException(status_code=422, detail="Body must contain 'html' and/or 'css'")

    output_dir = Path(settings.OUTPUT_DIR) / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    if new_html is not None:
        result.html_content = new_html
        (output_dir / "index.html").write_text(new_html, encoding="utf-8")

    if new_css is not None:
        result.css_content = new_css
        (output_dir / "styles.css").write_text(new_css, encoding="utf-8")

    result.user_modified = True
    logger.info("Job %s updated by user (html=%s, css=%s)", job_id, new_html is not None, new_css is not None)

    await job_manager.persist_content_update(
        job_id,
        html=result.html_content,
        css=result.css_content,
    )

    return JSONResponse(content={"status": "updated", "jobId": job_id})


@router.get("/{job_id}/download")
async def download_job(job_id: str) -> StreamingResponse:
    """Download the generated HTML/CSS as a ZIP file."""
    logger.info("Download requested for job %s", job_id)
    result = job_manager.get_result(job_id)
    if result is None:
        job = job_manager.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        raise HTTPException(
            status_code=400,
            detail=f"Job {job_id} has no results yet (status: {job.status.value})",
        )

    # Check if files exist on disk
    output_dir = Path(settings.OUTPUT_DIR) / job_id
    html_path = output_dir / "index.html"
    css_path = output_dir / "styles.css"

    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if html_path.exists():
            zf.write(html_path, "index.html")
        else:
            # Use content from result
            zf.writestr("index.html", result.html_content)

        if css_path.exists():
            zf.write(css_path, "styles.css")
        else:
            zf.writestr("styles.css", result.css_content)

        # Include assets in ZIP
        assets_dir = output_dir / "assets"
        if not assets_dir.exists():
            assets_dir = Path(settings.TEMP_DIR) / job_id / "assets"
        if assets_dir.exists():
            for asset_file in assets_dir.iterdir():
                if asset_file.is_file():
                    zf.write(asset_file, f"assets/{asset_file.name}")

        # Include diff images if available
        if result.verification:
            if result.verification.diff_image_path:
                diff_path = Path(result.verification.diff_image_path)
                if diff_path.exists():
                    zf.write(diff_path, "verification/diff_heatmap.png")

            if result.verification.figma_screenshot_path:
                figma_path = Path(result.verification.figma_screenshot_path)
                if figma_path.exists():
                    zf.write(figma_path, "verification/figma_screenshot.png")

            if result.verification.rendered_screenshot_path:
                rendered_path = Path(result.verification.rendered_screenshot_path)
                if rendered_path.exists():
                    zf.write(rendered_path, "verification/rendered_screenshot.png")

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="figma-export-{job_id[:8]}.zip"'
        },
    )


def _walk_nodes(
    node: dict[str, Any],
    target_ids: set[str],
    parent: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Walk a design-spec node tree and collect properties for target IDs."""
    result: dict[str, dict[str, Any]] = {}
    node_id = node.get("id", "")

    if node_id in target_ids:
        text_info = node.get("text")
        text_out: dict[str, Any] | None = None
        if text_info:
            seg = text_info.get("segments", [{}])[0] if text_info.get("segments") else {}
            text_out = {
                "fontSize": seg.get("fontSize", 16),
                "lineHeight": seg.get("lineHeight"),
                "lineHeightUnit": seg.get("lineHeightUnit", "AUTO"),
                "letterSpacing": seg.get("letterSpacing", 0),
                "letterSpacingUnit": seg.get("letterSpacingUnit", "PIXELS"),
                "paragraphSpacing": text_info.get("paragraphSpacing", 0),
                "textAlignHorizontal": text_info.get("textAlignHorizontal", "LEFT"),
                "segments": [
                    {
                        "characters": s.get("characters", ""),
                        "fontSize": s.get("fontSize", 16),
                        "lineHeight": s.get("lineHeight"),
                        "lineHeightUnit": s.get("lineHeightUnit", "AUTO"),
                        "letterSpacing": s.get("letterSpacing", 0),
                        "fontFamily": s.get("fontFamily", ""),
                        "fontWeight": s.get("fontWeight", 400),
                    }
                    for s in text_info.get("segments", [])
                ],
            }

        layout = node.get("layout", {})
        layout_out = {
            "mode": layout.get("mode", layout.get("type", "NONE")),
            "gap": layout.get("gap", layout.get("itemSpacing", 0)),
            "padding": {
                "top": layout.get("paddingTop", layout.get("padding", {}).get("top", 0) if isinstance(layout.get("padding"), dict) else 0),
                "right": layout.get("paddingRight", layout.get("padding", {}).get("right", 0) if isinstance(layout.get("padding"), dict) else 0),
                "bottom": layout.get("paddingBottom", layout.get("padding", {}).get("bottom", 0) if isinstance(layout.get("padding"), dict) else 0),
                "left": layout.get("paddingLeft", layout.get("padding", {}).get("left", 0) if isinstance(layout.get("padding"), dict) else 0),
            },
            "direction": layout.get("direction", layout.get("mode", "NONE")),
            "primaryAxisAlign": layout.get("primaryAxisAlign", "MIN"),
            "counterAxisAlign": layout.get("counterAxisAlign", "MIN"),
        }

        parent_layout_out: dict[str, Any] | None = None
        if parent:
            pl = parent.get("layout", {})
            parent_layout_out = {
                "mode": pl.get("mode", pl.get("type", "NONE")),
                "gap": pl.get("gap", pl.get("itemSpacing", 0)),
                "padding": {
                    "top": pl.get("paddingTop", pl.get("padding", {}).get("top", 0) if isinstance(pl.get("padding"), dict) else 0),
                    "right": pl.get("paddingRight", pl.get("padding", {}).get("right", 0) if isinstance(pl.get("padding"), dict) else 0),
                    "bottom": pl.get("paddingBottom", pl.get("padding", {}).get("bottom", 0) if isinstance(pl.get("padding"), dict) else 0),
                    "left": pl.get("paddingLeft", pl.get("padding", {}).get("left", 0) if isinstance(pl.get("padding"), dict) else 0),
                },
                "direction": pl.get("direction", pl.get("mode", "NONE")),
            }

        result[node_id] = {
            "text": text_out,
            "layout": layout_out,
            "parentLayout": parent_layout_out,
            "name": node.get("name", ""),
            "type": node.get("type", ""),
        }

    for child in node.get("children", []):
        result.update(_walk_nodes(child, target_ids, parent=node))

    return result


@router.get("/{job_id}/design-spec/nodes")
async def get_design_spec_nodes(
    job_id: str,
    ids: str = Query("", description="Comma-separated node IDs"),
) -> JSONResponse:
    """Return Figma design-spec properties for the requested node IDs."""
    spec_path = Path(settings.TEMP_DIR) / job_id / "design_spec.json"
    if not spec_path.exists():
        raise HTTPException(status_code=404, detail=f"Design spec not found for job {job_id}")

    try:
        spec_data = json_module.loads(spec_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read design spec: {e}")

    root = spec_data.get("root")
    if root is None:
        nodes_list = spec_data.get("nodes", [])
        root = nodes_list[0] if nodes_list else None
    if root is None:
        raise HTTPException(status_code=404, detail="No root node in design spec")

    target_ids = {i.strip() for i in ids.split(",") if i.strip()} if ids else set()
    if not target_ids:
        raise HTTPException(status_code=422, detail="Provide at least one node ID via ?ids=")

    nodes_map = _walk_nodes(root, target_ids)

    return JSONResponse(content={"nodes": nodes_map})


@router.post("/{job_id}/micro-fix")
async def micro_fix(job_id: str, body: MicroFixRequest) -> JSONResponse:
    """Apply a targeted AI fix to a specific element.

    Uses a lightweight GPT-4 call focused only on the selected node
    rather than re-running the full fixer pipeline.
    """
    result = job_manager.get_result(job_id)
    if result is None:
        job = job_manager.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        raise HTTPException(
            status_code=400,
            detail=f"Job {job_id} has no results yet (status: {job.status.value})",
        )

    from agents.micro_fixer import MicroFixerAgent

    agent = MicroFixerAgent(job_id=job_id)
    agent.set_progress_callback(job_manager.send_progress)

    try:
        fix_result = await agent.execute(
            node_id=body.nodeId,
            user_prompt=body.userPrompt,
            html_content=body.html,
            css_content=body.css,
        )
    except Exception as e:
        logger.error("Micro-fix failed for job %s: %s", job_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Micro-fix failed: {e}")

    if fix_result.get("changes_made"):
        output_dir = Path(settings.OUTPUT_DIR) / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        new_html = fix_result["html"]
        new_css = fix_result["css"]
        result.html_content = new_html
        result.css_content = new_css
        result.user_modified = True
        (output_dir / "index.html").write_text(new_html, encoding="utf-8")
        (output_dir / "styles.css").write_text(new_css, encoding="utf-8")
        await job_manager.persist_content_update(job_id, html=new_html, css=new_css)
        logger.info("Micro-fix applied for job %s node %s", job_id, body.nodeId)

    return JSONResponse(content={
        "html": fix_result["html"],
        "css": fix_result["css"],
        "changes_made": fix_result["changes_made"],
        "description": fix_result["description"],
    })
