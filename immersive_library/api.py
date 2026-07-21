import asyncio
import os
import time
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
from immersive_library.utils import enforce_rate_limit, update_precomputation

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


class RequestTooLarge(Exception):
    pass


class RequestSizeLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                await JSONResponse({"message": "Invalid Content-Length"}, status_code=400)(
                    scope, receive, send
                )
                return
            if declared_length < 0:
                await JSONResponse({"message": "Invalid Content-Length"}, status_code=400)(
                    scope, receive, send
                )
                return
            if declared_length > self.max_bytes:
                await JSONResponse({"message": "Request body too large"}, status_code=413)(
                    scope, receive, send
                )
                return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise RequestTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestTooLarge:
            await JSONResponse({"message": "Request body too large"}, status_code=413)(
                scope, receive, send
            )


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

app.add_middleware(
    RequestSizeLimitMiddleware,
    max_bytes=int(os.getenv("MAX_REQUEST_BYTES", str(2 * 1024 * 1024))),
)
app.add_middleware(GZipMiddleware, minimum_size=4096, compresslevel=6)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if request.method in {"POST", "PUT", "DELETE"}:
        try:
            await enforce_rate_limit(request, "write", 300, 60)
        except HTTPException as exc:
            return JSONResponse({"message": exc.detail}, status_code=exc.status_code)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response

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
async def setup_users():
    async with database.connection() as connection:
        await connection.execute("BEGIN IMMEDIATE")
        try:
            await connection.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    oid INTEGER PRIMARY KEY AUTOINCREMENT,
                    google_userid CHAR,
                    username CHAR,
                    moderator INTEGER,
                    banned INTEGER
                )
            """)
            await connection.execute("""
                CREATE TABLE IF NOT EXISTS user_tokens (
                    oid INTEGER PRIMARY KEY AUTOINCREMENT,
                    token CHAR NOT NULL UNIQUE,
                    userid INTEGER NOT NULL,
                    created_at INTEGER,
                    expires_at INTEGER
                )
            """)
            token_columns = await connection.fetch_all("PRAGMA table_info(user_tokens)")
            token_column_names = {column["name"] for column in token_columns}
            if "created_at" not in token_column_names:
                await connection.execute("ALTER TABLE user_tokens ADD COLUMN created_at INTEGER")
            if "expires_at" not in token_column_names:
                await connection.execute("ALTER TABLE user_tokens ADD COLUMN expires_at INTEGER")
            now = int(time.time())
            # TODO: Remove after the legacy-token migration/grace window is no longer needed.
            legacy_ttl = int(
                os.getenv("LEGACY_TOKEN_GRACE_SECONDS", str(90 * 24 * 60 * 60))
            )
            await connection.execute(
                "UPDATE user_tokens SET created_at=COALESCE(created_at, :now), expires_at=COALESCE(expires_at, :expires_at)",
                {"now": now, "expires_at": now + legacy_ttl},
            )
            await connection.execute("""
                CREATE TABLE IF NOT EXISTS auth_requests (
                    request_id TEXT PRIMARY KEY,
                    token_hash TEXT,
                    username TEXT NOT NULL,
                    return_to TEXT,
                    verification_code TEXT NOT NULL,
                    browser_nonce_hash TEXT,
                    expires_at INTEGER NOT NULL
                )
            """)

            # TODO: Remove once all production databases have migrated away from users.token.
            columns = await connection.fetch_all("PRAGMA table_info(users)")
            if any(column["name"] == "token" for column in columns):
                await connection.execute(
                    """
                    INSERT OR IGNORE INTO user_tokens
                        (token, userid, created_at, expires_at)
                    SELECT token, oid, :now, :expires_at
                    FROM users
                    WHERE token IS NOT NULL AND token != ''
                    """,
                    {"now": now, "expires_at": now + legacy_ttl},
                )
                await connection.execute("DROP INDEX IF EXISTS users_token")
                await connection.execute("ALTER TABLE users DROP COLUMN token")

            await connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS users_google_userid on users (google_userid)"
            )
            await connection.execute(
                "CREATE INDEX IF NOT EXISTS user_tokens_userid on user_tokens (userid)"
            )
            await connection.execute(
                "CREATE INDEX IF NOT EXISTS user_tokens_expires_at on user_tokens (expires_at)"
            )
            await connection.execute(
                "CREATE INDEX IF NOT EXISTS auth_requests_expires_at on auth_requests (expires_at)"
            )
        except BaseException:
            await connection.execute("ROLLBACK")
            raise
        else:
            await connection.execute("COMMIT")


# TODO: Remove this helper and its calls once all deployed databases have completed this cleanup migration.
async def _cleanup_relation_table(
    table: str, group_by: str, unique_index: str
) -> None:
    await database.execute(
        f"DELETE FROM {table} WHERE contentid NOT IN (SELECT oid FROM content)"
    )
    await database.execute(
        f"""
        DELETE FROM {table}
        WHERE rowid NOT IN (
            SELECT MIN(rowid) FROM {table} GROUP BY {group_by}
        )
        """
    )
    await database.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {unique_index} on {table} ({group_by})"
    )


async def setup():
    await setup_users()

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
    await _cleanup_relation_table(
        "reports", "userid, contentid, reason", "reports_user_content_reason"
    )

    # Likes
    await database.execute(
        "CREATE TABLE IF NOT EXISTS likes (userid INTEGER, contentid INTEGER)"
    )
    await database.execute("CREATE INDEX IF NOT EXISTS likes_userid on likes (userid)")
    await database.execute(
        "CREATE INDEX IF NOT EXISTS likes_contentid on likes (contentid)"
    )
    await _cleanup_relation_table(
        "likes", "userid, contentid", "likes_userid_contentid"
    )

    # Tags
    await database.execute(
        "CREATE TABLE IF NOT EXISTS tags (contentid INTEGER, tag CHAR)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS tags_contentid on tags (contentid)"
    )
    await _cleanup_relation_table(
        "tags", "contentid, tag", "tags_contentid_tag"
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
