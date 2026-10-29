import asyncio
import os
import time
from collections.abc import Awaitable, Callable

from loguru import logger

from immersive_library.database import database
from immersive_library.database.backup import create_daily_backup
from immersive_library.neighbors import compute_neighbors
from immersive_library.projects import register_projects
from immersive_library.services import descriptions
from immersive_library.services.recommendations import refresh_quality_ranks
from immersive_library.utils import DAY, refresh_recent_likes

HOUR = 3600
RETRY_SECONDS = 300
CHECK_SECONDS = 60

DESCRIPTION_IDLE_SECONDS = 30
DESCRIPTION_ATTEMPTS = 3
DESCRIPTION_MAX_BACKOFF_SECONDS = 3600


async def refresh_rankings() -> None:
    await refresh_recent_likes(database)
    await refresh_quality_ranks(database)


async def backup() -> None:
    await asyncio.to_thread(create_daily_backup)


async def neighbors() -> None:
    await asyncio.to_thread(compute_neighbors)


# Jobs and their intervals. All run at startup, which also covers missed runs.
# The backup checks hourly and skips days that already have one.
JOBS: dict[Callable[[], Awaitable[None]], int] = {
    backup: HOUR,
    refresh_rankings: HOUR,
    neighbors: DAY,
}


async def run_jobs() -> None:
    due = dict.fromkeys(JOBS, 0.0)
    while True:
        for job, interval in JOBS.items():
            if time.monotonic() < due[job]:
                continue
            try:
                await job()
                due[job] = time.monotonic() + interval
            except Exception:
                logger.exception(
                    "Job {} failed, retrying in {} s", job.__name__, RETRY_SECONDS
                )
                due[job] = time.monotonic() + RETRY_SECONDS
        await asyncio.sleep(CHECK_SECONDS)


async def describe_assets() -> None:
    """Describes one asset after another, rendering each through the app."""
    base_url = os.getenv("RENDER_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    empty_preview = descriptions.blank_preview()

    # Failures other than AssetError, such as an unreachable API, usually affect
    # every asset, so the worker backs off and retries the same asset. One that
    # keeps failing is postponed, so it cannot block the others.
    failures = 0
    attempts: dict[int, int] = {}
    postponed: dict[int, float] = {}
    while True:
        now = time.monotonic()
        postponed = {i: until for i, until in postponed.items() if until > now}
        job = None
        try:
            job = await descriptions.take_next(set(postponed))
            if job is None:
                await asyncio.sleep(DESCRIPTION_IDLE_SECONDS)
                continue
            await descriptions.describe_asset(*job, base_url, empty_preview)
            failures = 0
            attempts.pop(job[0]["content_id"], None)
        except Exception:
            delay = min(
                DESCRIPTION_IDLE_SECONDS * 2**failures, DESCRIPTION_MAX_BACKOFF_SECONDS
            )
            failures += 1
            logger.exception("Description failed, retrying in {} s", delay)
            if job is not None:
                content_id = job[0]["content_id"]
                attempts[content_id] = attempts.get(content_id, 0) + 1
                if attempts[content_id] >= DESCRIPTION_ATTEMPTS:
                    logger.warning("Postponing asset {} for a day", content_id)
                    postponed[content_id] = time.monotonic() + DAY
                    del attempts[content_id]
            await asyncio.sleep(delay)


async def run() -> None:
    """Runs the background jobs. Exactly one worker process may run."""
    register_projects()
    await database.connect()
    try:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(run_jobs())
            if os.getenv("OPENROUTER_API_KEY"):
                tasks.create_task(describe_assets())
            else:
                logger.info("OPENROUTER_API_KEY is not set, assets are not described")
    finally:
        await database.disconnect()


if __name__ == "__main__":
    asyncio.run(run())
