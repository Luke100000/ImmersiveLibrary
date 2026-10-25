import asyncio
import os
from contextlib import asynccontextmanager
from functools import partial
from typing import Any

import orjson
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi_cache import Coder, FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from prometheus_fastapi_instrumentator import Instrumentator
from redis import asyncio as aioredis
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import JSONResponse

from immersive_library.caching import CachedStaticFiles, apply_cache_policy
from immersive_library.database import database
from immersive_library.database.schema import initialize_database
from immersive_library.rendering import BrowserRenderer
from immersive_library.routers import router
from immersive_library.utils import update_precomputation

description = """
A simple and generic user asset library.
"""

tags_metadata = [
    {
        "name": "Auth",
        "description": "Authentication happens via Google Sign-In, the verified userid serves as unique identifier to a users account. On authentication, the user supplies it's access token, which it then uses for all API calls requiring authentication.",
    },
    {
        "name": "Content",
        "description": "A content is assigned to a project, contains a json metadata and a raw blob data field.",
    },
    {
        "name": "Likes",
        "description": "A content can be liked, raising the accumulated like counter on the content as well as providing a way to list a users liked content. Can also be used for a content subscription model.",
    },
    {
        "name": "Tags",
        "description": "The owner or moderator can add and remove tags used to filter content.",
    },
    {
        "name": "Users",
        "description": "A user is a unique, authenticated account with a non unique, changeable username. A user is required to interact with most API calls.",
    },
    {
        "name": "Admin",
        "description": "Administrative tools",
    },
]


class FastAPIJsonCoder(Coder):
    """
    Basically only required to get the exclude_none flag through the cache.
    """

    @classmethod
    def encode(cls, value: Any) -> bytes:
        return orjson.dumps(
            value,
            default=partial(jsonable_encoder, exclude_none=True),
            option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY,
        )

    @classmethod
    def decode(cls, value: bytes) -> Any:
        return orjson.loads(value)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await database.connect()
    await initialize_database(database)
    asyncio.create_task(update_precomputation(database))

    redis = aioredis.from_url(
        "redis://"
        + os.getenv("REDIS_HOST", "localhost")
        + ":"
        + os.getenv("REDIS_PORT", "6379")
    )
    FastAPICache.init(
        RedisBackend(redis), prefix="immersive-library", coder=FastAPIJsonCoder
    )

    renderer = BrowserRenderer()
    _app.state.renderer = renderer
    try:
        yield
    finally:
        try:
            await renderer.close()
        finally:
            await database.disconnect()


app = FastAPI(
    title="Immersive Library",
    version="0.0.1",
    description=description,
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=4096, compresslevel=6)

app.mount("/static", CachedStaticFiles(directory="static"), name="static")


@app.middleware("http")
async def cache_control_middleware(request: Request, call_next):
    response = await call_next(request)
    apply_cache_policy(request, response)
    return response


# Prometheus integration
instrumentator = Instrumentator().instrument(app)

instrumentator.expose(app)


@app.exception_handler(HTTPException)
async def validation_exception_handler(request: Request, exc: HTTPException):
    assert request
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail},
    )


app.include_router(router)
