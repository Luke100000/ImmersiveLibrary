import math
import os
import time

from fastapi import Header, HTTPException, Request
from limits import parse_many
from limits.aio.storage import RedisStorage
from limits.aio.strategies import SlidingWindowCounterRateLimiter
from limits.errors import StorageError
from loguru import logger

from immersive_library.database import database
from immersive_library.utils import token_to_user_id

limiter = SlidingWindowCounterRateLimiter(
    RedisStorage(
        "async+redis://"
        + os.getenv("REDIS_HOST", "localhost")
        + ":"
        + os.getenv("REDIS_PORT", "6379"),
        implementation="redispy",
        wrap_exceptions=True,
        key_prefix="immersive-library:limits",
    )
)


def client_ip(request: Request) -> str:
    return f"ip:{request.client.host if request.client else 'unknown'}"


class RateLimit:
    """
    Limits requests per user, or per IP for anonymous requests.
    Fails open, so a Redis outage never blocks clients.
    """

    def __init__(self, name: str, limits: str):
        self.name = name
        self.items = parse_many(limits)

    async def __call__(
        self,
        request: Request,
        token: str | None = None,
        authorization: str = Header(None),
    ) -> None:
        user_id = await token_to_user_id(database, token, authorization)
        await self.hit(f"user:{user_id}" if user_id is not None else client_ip(request))

    async def hit(self, identity: str) -> None:
        try:
            for item in self.items:
                if not await limiter.hit(item, self.name, identity):
                    stats = await limiter.get_window_stats(item, self.name, identity)
                    retry_after = max(1, math.ceil(stats.reset_time - time.time()))
                    raise HTTPException(
                        429,
                        f"Too many requests, try again in {retry_after} seconds",
                        headers={"Retry-After": str(retry_after)},
                    )
        except StorageError:
            logger.opt(exception=True).warning("Rate limiter unavailable")


# Deliberately generous, clients don't handle 429 yet.
AUTH = RateLimit("auth", "60/minute")
UPLOAD = RateLimit("upload", "60/hour;300/day")
UPDATE = RateLimit("update", "300/hour")

# Likes, reports, tags and collection edits share one budget.
INTERACT = RateLimit("interact", "300/minute;5000/day")

# Only counted when a preview actually needs the browser.
RENDER = RateLimit("render", "120/minute;2000/hour")
