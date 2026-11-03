import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from tempfile import NamedTemporaryFile
from weakref import WeakValueDictionary

import orjson
from fastapi import HTTPException
from fastapi_cache import FastAPICache
from loguru import logger
from redis.exceptions import RedisError
from starlette.concurrency import run_in_threadpool

from immersive_library.database import database
from immersive_library.previews import (
    JPEG_QUALITY,
    MASTER_SIZE,
    make_grid,
    make_preview,
)
from immersive_library.ratelimit import RENDER
from immersive_library.rendering import BrowserRenderer
from immersive_library.services import content as content_service

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
    renderer: BrowserRenderer,
    identity: str,
    project: str,
    content_id: int,
    version: int,
) -> bytes:
    """The full size render, from the disk cache or the browser."""
    bucket = f"{content_id % 256:02x}"
    cache_path = CACHE_DIR / project / bucket / f"{content_id}_{version}.png"
    try:
        return await run_in_threadpool(cache_path.read_bytes)
    except FileNotFoundError:
        pass

    # Only counted when a preview actually needs the browser.
    await RENDER.hit(identity)
    content = await content_service.get_content(project, content_id)
    try:
        png_bytes = await renderer.render_png(
            project, content, width=MASTER_SIZE[0], height=MASTER_SIZE[1]
        )
    except Exception as exc:
        raise HTTPException(500, f"Render failed: {exc}") from exc

    await run_in_threadpool(write_render_cache, cache_path, png_bytes)
    return png_bytes


async def cached_jpeg(
    lock_key: str, cache_key: str, produce: Callable[[], Awaitable[bytes]]
) -> bytes:
    backend = FastAPICache.get_backend()
    cache_key = f"{FastAPICache.get_prefix()}:render:{cache_key}:jpeg{JPEG_QUALITY}"

    async with render_locks.setdefault(lock_key, asyncio.Lock()):
        try:
            jpeg_bytes = await backend.get(cache_key)
        except RedisError:
            logger.opt(exception=True).warning("Could not read preview cache")
            jpeg_bytes = None

        if jpeg_bytes is None:
            jpeg_bytes = await produce()
            try:
                await backend.set(cache_key, jpeg_bytes, expire=PREVIEW_CACHE_SECONDS)
            except RedisError:
                logger.opt(exception=True).warning("Could not write preview cache")

    return jpeg_bytes


async def content_preview(
    renderer: BrowserRenderer,
    identity: str,
    project: str,
    content_id: int,
    size: tuple[int, int],
) -> bytes:
    version = await database.fetch_val(
        "SELECT version FROM content WHERE oid=:content_id AND project=:project",
        {"content_id": content_id, "project": project},
    )
    if version is None:
        raise HTTPException(404, "Content not found")

    async def produce() -> bytes:
        master = await get_master(renderer, identity, project, content_id, version)
        return await run_in_threadpool(make_preview, master, size)

    asset_key = f"{project}:{content_id}"
    return await cached_jpeg(
        asset_key, f"{asset_key}:{version}:{size[0]}x{size[1]}", produce
    )


async def grid_preview(
    renderer: BrowserRenderer,
    identity: str,
    project: str,
    key: str,
    content_ids: list[int],
) -> bytes:
    """Up to six assets in one image, for link previews of users and collections."""
    rows = await database.fetch_all(
        "SELECT oid, version FROM content WHERE oid IN (SELECT value FROM json_each(:ids))",
        {"ids": orjson.dumps(content_ids).decode()},
    )
    versions = {row["oid"]: row["version"] for row in rows}
    content_ids = [content_id for content_id in content_ids if content_id in versions]
    if not content_ids:
        raise HTTPException(404, "Nothing to preview")

    async def locked_master(content_id: int) -> bytes:
        # Shares the lock with content_preview, so an asset renders once.
        async with render_locks.setdefault(f"{project}:{content_id}", asyncio.Lock()):
            return await get_master(
                renderer, identity, project, content_id, versions[content_id]
            )

    async def produce() -> bytes:
        masters = await asyncio.gather(*map(locked_master, content_ids))
        return await run_in_threadpool(make_grid, masters)

    fingerprint = ",".join(f"{oid}_{versions[oid]}" for oid in content_ids)
    return await cached_jpeg(
        f"{project}:{key}", f"{project}:{key}:{fingerprint}", produce
    )
