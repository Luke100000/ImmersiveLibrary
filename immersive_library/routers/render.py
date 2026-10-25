import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from immersive_library.common import projects
from immersive_library.database import database
from immersive_library.enums import RenderPreset
from immersive_library.rendering import BrowserRenderer
from immersive_library.services import content as content_service

router = APIRouter(tags=["Content"])


RENDER_PRESET_SIZES: dict[RenderPreset, tuple[int, int]] = {
    RenderPreset.EMBED: (1200, 630),
    RenderPreset.ICON: (256, 256),
    RenderPreset.THUMBNAIL: (512, 512),
    RenderPreset.SQUARE: (1024, 1024),
}

CACHE_DIR = Path("data/cache")


def write_render_cache(cache_path: Path, png_bytes: bytes) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = NamedTemporaryFile(dir=cache_path.parent, delete=False)
    try:
        with temporary:
            temporary.write(png_bytes)
        Path(temporary.name).replace(cache_path)
    finally:
        Path(temporary.name).unlink(missing_ok=True)


@router.get("/v1/render/{project}/{contentid}", response_class=Response)
async def render_content_png(
    request: Request,
    project: str,
    contentid: int,
    preset: RenderPreset = Query(RenderPreset.EMBED),
) -> Response:
    if project not in projects:
        raise HTTPException(404, "Project not found")

    record = await database.fetch_one(
        "SELECT version FROM content WHERE oid=:contentid AND project=:project",
        {"contentid": contentid, "project": project},
    )
    if record is None:
        raise HTTPException(404, "Content not found")

    width, height = RENDER_PRESET_SIZES[preset]
    cache_name = f"{contentid}_{record['version']}_{width}x{height}.png"
    cache_path = CACHE_DIR / cache_name
    cache_headers = {
        "Cache-Control": "public, max-age=300, must-revalidate",
    }
    try:
        png_bytes = await run_in_threadpool(cache_path.read_bytes)
    except FileNotFoundError:
        pass
    else:
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers=cache_headers,
        )

    render_url = request.app.url_path_for("get_render_shell").make_absolute_url(
        os.getenv("RENDER_BASE_URL", "http://127.0.0.1:8000")
    )

    content = await content_service.get_content(project, contentid)
    try:
        renderer: BrowserRenderer = request.app.state.renderer
        png_bytes = await renderer.render_png(
            str(render_url), project, content, width=width, height=height
        )
    except Exception as exc:
        raise HTTPException(500, f"Render failed: {exc}") from exc

    await run_in_threadpool(write_render_cache, cache_path, png_bytes)
    return Response(content=png_bytes, media_type="image/png", headers=cache_headers)
