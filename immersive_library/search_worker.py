import asyncio
from pathlib import Path

from filelock import AsyncFileLock
from loguru import logger

from immersive_library.database import database
from immersive_library.utils import refresh_recent_likes

REFRESH_SECONDS = 3600
RETRY_SECONDS = 60


async def run() -> None:
    lock_path = Path(database.url.database).with_name("search.lock")
    async with AsyncFileLock(lock_path, poll_interval=1):
        while True:
            try:
                await refresh_recent_likes(database)
                await asyncio.sleep(REFRESH_SECONDS)
            except Exception:
                logger.exception(
                    "Search worker failed, retrying in {} s", RETRY_SECONDS
                )
                await asyncio.sleep(RETRY_SECONDS)
