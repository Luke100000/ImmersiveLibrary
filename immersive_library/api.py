import asyncio
import os
from contextlib import asynccontextmanager
from functools import partial
from typing import Any

import orjson
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.openapi.utils import get_openapi
from fastapi_cache import Coder, FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from prometheus_fastapi_instrumentator import Instrumentator
from redis import asyncio as aioredis
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from immersive_library.common import database
from immersive_library.routers import (
    auth,
    content,
    like,
    misc,
    report,
    tag,
    tools,
    user,
    viewer,
)
from immersive_library.routers.deprecated import content as deprecated_content
from immersive_library.routers.deprecated import user as deprecated_user
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
    await setup()

    redis = aioredis.from_url(
        "redis://"
        + os.getenv("REDIS_HOST", "localhost")
        + ":"
        + os.getenv("REDIS_PORT", "6379")
    )
    FastAPICache.init(
        RedisBackend(redis), prefix="immersive-library", coder=FastAPIJsonCoder
    )

    yield

    await database.disconnect()


app = FastAPI(lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=4096, compresslevel=6)

app.mount("/static", StaticFiles(directory="static"), name="static")


# Custom OpenAPI to fix the missing description
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="Immersive Library",
        version="0.0.1",
        description=description,
        routes=app.routes,
    )

    openapi_schema["tags"] = tags_metadata

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


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


# Create tables
async def setup():
    # Users
    await database.execute("""
        CREATE TABLE IF NOT EXISTS users (
            oid INTEGER PRIMARY KEY AUTOINCREMENT,
            google_userid CHAR,
            token CHAR,
            username CHAR,
            moderator INTEGER,
            banned INTEGER
        )
    """)
    await database.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS users_google_userid on users (google_userid)"
    )
    await database.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS users_token on users (token)"
    )

    # Content
    await database.execute("""
        CREATE TABLE IF NOT EXISTS content (
            oid INTEGER PRIMARY KEY AUTOINCREMENT,
            userid INTEGER,
            project CHAR,
            title CHAR,
            version int DEFAULT 0,
            meta TEXT,
            data BLOB
        )
    """)
    await database.execute(
        "CREATE INDEX IF NOT EXISTS content_userid on content (userid)"
    )

    # Reports
    await database.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            userid INTEGER,
            contentid INTEGER,
            reason CHAR
        )
    """)
    await database.execute(
        "CREATE INDEX IF NOT EXISTS reports_userid on reports (userid)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS reports_contentid on reports (contentid)"
    )

    # Likes
    await database.execute(
        "CREATE TABLE IF NOT EXISTS likes (userid INTEGER, contentid INTEGER)"
    )
    await database.execute("CREATE INDEX IF NOT EXISTS likes_userid on likes (userid)")
    await database.execute(
        "CREATE INDEX IF NOT EXISTS likes_contentid on likes (contentid)"
    )

    # Tags
    await database.execute(
        "CREATE TABLE IF NOT EXISTS tags (contentid INTEGER, tag CHAR)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS tags_contentid on tags (contentid)"
    )

    # Precomputation
    await database.execute("""
        CREATE TABLE IF NOT EXISTS precomputation (
            contentid INTEGER PRIMARY KEY,
            tags CHAR,
            likes INTEGER,
            reports INTEGER
        ) WITHOUT ROWID
    """)

    asyncio.create_task(update_precomputation(database))


# Deprecated routes
app.include_router(deprecated_content.router)
app.include_router(deprecated_user.router)

# Latest routes
app.include_router(auth.router)
app.include_router(content.router)
app.include_router(like.router)
app.include_router(misc.router)
app.include_router(report.router)
app.include_router(tag.router)
app.include_router(tools.router)
app.include_router(user.router)
app.include_router(viewer.router)
