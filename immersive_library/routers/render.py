import asyncio
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from weakref import WeakValueDictionary

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi_cache import FastAPICache
from loguru import logger
from redis.exceptions import RedisError
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from immersive_library.common import projects
from immersive_library.database import database
from immersive_library.enums import RenderPreset
from immersive_library.previews import JPEG_QUALITY, MASTER_SIZE, make_preview
from immersive_library.rendering import BrowserRenderer
from immersive_library.services import content as content_service

router = APIRouter(tags=["Content"])


RENDER_PRESET_SIZES: dict[RenderPreset, tuple[int, int]] = {
    RenderPreset.ICON: (256, 256),
    RenderPreset.THUMBNAIL: (512, 512),
    RenderPreset.EMBED: MASTER_SIZE,
}

CACHE_DIR = Path(database.url.database).parent / "cache"
PREVIEW_CACHE_SECONDS = 300

render_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


def write_render_cache(cache_path: Path, png_bytes: bytes) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = NamedTemporaryFile(dir=cache_path.parent, delete=False)
    try:
        with temporary:
            temporary.write(png_bytes)
        Path(temporary.name).replace(cache_path)
    finally:
        Path(temporary.name).unlink(missing_ok=True)

    content_id, version = cache_path.stem.split("_")
    prefix = f"{content_id}_"
    for previous in cache_path.parent.glob(f"{prefix}*.png"):
        previous_version = previous.stem.removeprefix(prefix)
        if previous_version.isdecimal() and int(previous_version) < int(version):
            previous.unlink(missing_ok=True)


async def get_master(
    request: Request, project: str, content_id: int, version: int
) -> bytes:
    bucket = f"{content_id % 256:02x}"
    cache_path = CACHE_DIR / project / bucket / f"{content_id}_{version}.png"
    try:
        return await run_in_threadpool(cache_path.read_bytes)
    except FileNotFoundError:
        pass

    render_url = request.app.url_path_for("get_render_shell").make_absolute_url(
        os.getenv("RENDER_BASE_URL", "http://127.0.0.1:8000")
    )
    content = await content_service.get_content(project, content_id)
    try:
        renderer: BrowserRenderer = request.app.state.renderer
        png_bytes = await renderer.render_png(
            str(render_url),
            project,
            content,
            width=MASTER_SIZE[0],
            height=MASTER_SIZE[1],
        )
    except Exception as exc:
        raise HTTPException(500, f"Render failed: {exc}") from exc

    await run_in_threadpool(write_render_cache, cache_path, png_bytes)
    return png_bytes


@router.get(
    "/v1/render/{project}/{content_id}",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
async def render_content(
    request: Request,
    project: str,
    content_id: int,
    preset: RenderPreset = Query(RenderPreset.EMBED),
) -> Response:
    if project not in projects:
        raise HTTPException(404, "Project not found")

    record = await database.fetch_one(
        "SELECT version FROM content WHERE oid=:content_id AND project=:project",
        {"content_id": content_id, "project": project},
    )
    if record is None:
        raise HTTPException(404, "Content not found")

    size = RENDER_PRESET_SIZES[preset]
    asset_key = f"{project}:{content_id}"
    cache_key = (
        f"{FastAPICache.get_prefix()}:render:{asset_key}:"
        f"{record['version']}:{size[0]}x{size[1]}:jpeg{JPEG_QUALITY}"
    )
    backend = FastAPICache.get_backend()
    lock = render_locks.setdefault(asset_key, asyncio.Lock())

    async with lock:
        try:
            jpeg_bytes = await backend.get(cache_key)
        except RedisError:
            logger.opt(exception=True).warning("Could not read preview cache")
            jpeg_bytes = None

        if jpeg_bytes is None:
            master = await get_master(request, project, content_id, record["version"])
            jpeg_bytes = await run_in_threadpool(make_preview, master, size)
            try:
                await backend.set(cache_key, jpeg_bytes, expire=PREVIEW_CACHE_SECONDS)
            except RedisError:
                logger.opt(exception=True).warning("Could not write preview cache")

    return Response(
        content=jpeg_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control": f"public, max-age={PREVIEW_CACHE_SECONDS}, must-revalidate"
        },
    )
