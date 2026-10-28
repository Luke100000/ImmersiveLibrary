import asyncio
import time
from collections.abc import Awaitable, Callable

from loguru import logger

from immersive_library.database import database
from immersive_library.database.backup import create_daily_backup
from immersive_library.neighbors import compute_neighbors
from immersive_library.services.recommendations import refresh_quality_ranks
from immersive_library.utils import DAY, refresh_recent_likes

HOUR = 3600
RETRY_SECONDS = 300
CHECK_SECONDS = 60


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


async def run() -> None:
    """Runs the background jobs. Exactly one worker process may run."""
    await database.connect()
    due = dict.fromkeys(JOBS, 0.0)
    try:
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
    finally:
        await database.disconnect()


if __name__ == "__main__":
    asyncio.run(run())
