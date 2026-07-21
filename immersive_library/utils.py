import asyncio
import base64
import hashlib
import os
import time
from typing import Any, Dict, Optional

import orjson
from cachetools import cached
from databases import Database
from databases.interfaces import Record
from fastapi import Cookie, Header, HTTPException, Path, Request

import immersive_library.common as common
from immersive_library.models import (
    Content,
    LiteContent,
    LiteUser,
    User,
)

MAX_USER_TOKENS = 10
TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", str(30 * 24 * 60 * 60)))
SESSION_COOKIE = "immersive_session"
PROTECTED_TAGS = frozenset({"invalid"})

_rate_limit_lock = asyncio.Lock()
_rate_limit_buckets: dict[tuple[str, str], tuple[int, float]] = {}


async def enforce_rate_limit(
    request: Request, bucket: str, limit: int, window_seconds: int
) -> None:
    identity = request.client.host if request.client is not None else "unknown"
    key = (bucket, identity)
    now = time.monotonic()
    async with _rate_limit_lock:
        count, reset_at = _rate_limit_buckets.get(key, (0, now + window_seconds))
        if now >= reset_at:
            count, reset_at = 0, now + window_seconds
        if count >= limit:
            raise HTTPException(429, "Too many requests")
        _rate_limit_buckets[key] = (count + 1, reset_at)
        if len(_rate_limit_buckets) > 10000:
            expired = [k for k, (_, reset) in _rate_limit_buckets.items() if now >= reset]
            for expired_key in expired:
                _rate_limit_buckets.pop(expired_key, None)


async def update_precomputation(database: Database, contentid: Optional[int] = None):
    """
    Refreshes the database persistent cache
    :param database: The database to refresh
    :param contentid: The contentid to refresh, or None to refresh all
    """
    await database.execute(
        f"""
        INSERT OR REPLACE
        INTO precomputation (contentid, tags, likes, reports)
        SELECT content.oid,
               CASE WHEN tagged_content.c_tags is NULL THEN '' ELSE tagged_content.c_tags END as tags,
               CASE WHEN liked_content.c_likes is NULL THEN 0 ELSE liked_content.c_likes END  as likes,
               CASE WHEN reported_c.reports is NULL THEN 0 ELSE reported_c.reports END        as reports 
        FROM content
        
         LEFT JOIN (SELECT likes.contentid, COUNT(*) as c_likes
                    FROM likes
                    GROUP BY likes.contentid) liked_content ON liked_content.contentid = content.oid

         LEFT JOIN (SELECT tags.contentid, GROUP_CONCAT(tag, ',') as c_tags
                    FROM tags
                    GROUP BY tags.contentid) tagged_content on tagged_content.contentid = content.oid

         LEFT JOIN (SELECT reports.contentid, COUNT(*) as reports
                    FROM reports
                    WHERE reports.reason = 'DEFAULT'
                    GROUP BY reports.contentid) reported_c on reported_c.contentid = content.oid
                    
        {"" if contentid is None else "WHERE content.oid = :contentid"}
    """,
        {} if contentid is None else {"contentid": contentid},
    )


@cached(cache={})
def get_base_select(include_data: bool, include_meta: bool, include_liked: bool = False):
    prompt = """
        SELECT c.oid,
               c.userid,
               users.username,
               c.title,
               c.version,
               c.meta,
               c.data,
               precomputation.likes,
               precomputation.tags,
               precomputation.reports
        FROM content c
            INNER JOIN users ON c.userid = users.oid
            INNER JOIN precomputation ON c.oid = precomputation.contentid
    """

    if include_liked:
        prompt = prompt.replace(
            "               precomputation.reports",
            """               precomputation.reports,
               EXISTS (
                   SELECT 1
                   FROM likes viewer_likes
                   WHERE viewer_likes.userid = :viewer_userid
                     AND viewer_likes.contentid = c.oid
               ) as is_liked""",
        )

    if not include_meta:
        prompt = prompt.replace("c.meta,", "")

    if not include_data:
        prompt = prompt.replace("c.data,", "")

    return prompt


def sha256(string: str) -> str:
    sha256_hash = hashlib.sha256()
    sha256_hash.update(string.encode("utf-8"))
    return sha256_hash.hexdigest()


def token_hash_from_credentials(
    authorization: Optional[str], session_token: Optional[str]
) -> Optional[str]:
    raw_token = session_token
    if authorization is not None and authorization.startswith("Bearer "):
        raw_token = authorization[7:].strip()
    if raw_token is None or len(raw_token) < 16:
        return None
    return sha256(raw_token)


async def token_to_userid(
    database: Database,
    authorization: Optional[str] = None,
    session_token: Optional[str] = None,
) -> Optional[int]:
    """Return the active, non-banned user for an Authorization header or session."""
    token_hash = token_hash_from_credentials(authorization, session_token)
    if token_hash is None:
        return None
    userid = await database.fetch_one(
        """
        SELECT user_tokens.userid
        FROM user_tokens
        INNER JOIN users ON users.oid = user_tokens.userid
        WHERE user_tokens.token=:token
          AND user_tokens.expires_at > :now
          AND users.banned = 0
        """,
        {"token": token_hash, "now": int(time.time())},
    )
    return None if userid is None else userid[0]


async def revoke_token(
    database: Database,
    authorization: Optional[str] = None,
    session_token: Optional[str] = None,
) -> None:
    token_hash = token_hash_from_credentials(authorization, session_token)
    if token_hash is not None:
        await database.execute(
            "DELETE FROM user_tokens WHERE token=:token", {"token": token_hash}
        )


async def get_count(database: Database, query: str, params: dict[str, Any]):
    row = await database.fetch_one(query, params)
    return row[0] if row is not None else 0


async def exists(database: Database, query: str, params: dict[str, Any]):
    return await get_count(database, query, params) > 0


async def user_exists(database: Database, userid: int) -> bool:
    """
    Checks if the user with the given userid exists
    """
    return await exists(
        database, "SELECT count(*) FROM users WHERE oid=:userid", {"userid": userid}
    )


async def login_user(database: Database, google_userid, username, token_hash):
    """Create/update a user and register one expiring hashed access token."""
    now = int(time.time())
    async with database.transaction():
        await database.execute(
            """
            INSERT INTO users (google_userid, username, moderator, banned)
            VALUES (:google_userid, :username, FALSE, FALSE)
            ON CONFLICT (google_userid) DO UPDATE SET username=:username
            """,
            {"google_userid": google_userid, "username": username},
        )
        user = await database.fetch_one(
            "SELECT oid, banned FROM users WHERE google_userid=:google_userid",
            {"google_userid": google_userid},
        )
        userid = user["oid"]
        if user["banned"]:
            raise HTTPException(403, "User is banned")

        await database.execute(
            "DELETE FROM user_tokens WHERE token=:token",
            {"token": token_hash},
        )

        await database.execute(
            """
            INSERT INTO user_tokens (token, userid, created_at, expires_at)
            VALUES (:token, :userid, :created_at, :expires_at)
            """,
            {
                "token": token_hash,
                "userid": userid,
                "created_at": now,
                "expires_at": now + TOKEN_TTL_SECONDS,
            },
        )

        # Drop old tokens
        await database.execute(
            """
            DELETE FROM user_tokens
            WHERE userid=:userid AND oid NOT IN (
                SELECT oid
                FROM user_tokens
                WHERE userid=:userid
                ORDER BY oid DESC
                LIMIT :max_tokens
            )
            """,
            {"userid": userid, "max_tokens": MAX_USER_TOKENS},
        )


async def owns_content(database: Database, project: str, contentid: int, userid: int) -> bool:
    """Check ownership within the project named by the route."""
    return await exists(
        database,
        """
        SELECT count(*) FROM content
        WHERE userid=:userid AND oid=:contentid AND project=:project
        """,
        {"userid": userid, "contentid": contentid, "project": project},
    )


async def content_exists(database: Database, project: str, contentid: int) -> bool:
    return await exists(
        database,
        "SELECT count(*) FROM content WHERE oid=:contentid AND project=:project",
        {"contentid": contentid, "project": project},
    )


async def is_moderator(database: Database, userid: int) -> bool:
    """
    Checks if the user is a moderator
    """
    return await exists(
        database,
        "SELECT count(*) FROM users WHERE oid=:userid AND moderator=TRUE AND banned=FALSE",
        {"userid": userid},
    )


async def is_banned(database: Database, userid: int) -> bool:
    """
    Checks if the user is banned
    """
    return await exists(
        database,
        "SELECT count(*) FROM users WHERE oid=:userid AND banned=TRUE",
        {"userid": userid},
    )


async def set_moderator(database: Database, userid: int, moderator: bool):
    """
    Sets moderator status
    """
    await database.execute(
        "UPDATE users SET moderator=:moderator WHERE oid=:userid",
        {"moderator": moderator, "userid": userid},
    )


async def set_banned(database: Database, userid: int, banned: bool):
    """Set banned status and immediately revoke all active sessions when banning."""
    async with database.transaction():
        await database.execute(
            "UPDATE users SET banned=:banned WHERE oid=:userid",
            {"banned": banned, "userid": userid},
        )
        if banned:
            await database.execute(
                "DELETE FROM user_tokens WHERE userid=:userid", {"userid": userid}
            )


async def has_liked(database: Database, userid: int, contentid: int):
    """
    Checks if the given user has liked the content
    """
    return await exists(
        database,
        "SELECT count(*) FROM likes WHERE userid=:userid AND contentid=:contentid",
        {"userid": userid, "contentid": contentid},
    )


async def has_reported(
    database: Database, userid: int, contentid: int, reason: str
) -> object:
    """
    Checks if the given user has reported the content with the given reason
    """
    return await exists(
        database,
        "SELECT count(*) FROM reports WHERE userid=:userid AND contentid=:contentid AND reason=:reason",
        {"userid": userid, "contentid": contentid, "reason": reason},
    )


async def has_tag(database: Database, contentid: int, tag: str) -> bool:
    """
    Checks if the given content has a given tag
    """
    return await exists(
        database,
        "SELECT count(*) FROM tags WHERE tag=:tag AND contentid=:contentid",
        {"tag": tag, "contentid": contentid},
    )


async def set_tags(database: Database, contentid: int, tags: list[str]):
    """Replace user-editable tags while preserving server-owned moderation tags."""
    if PROTECTED_TAGS.intersection(tags):
        raise HTTPException(400, "Protected tags cannot be supplied in content metadata")

    await database.execute(
        "DELETE FROM tags WHERE contentid=:contentid AND tag != 'invalid'",
        {"contentid": contentid},
    )

    for tag in dict.fromkeys(tags):
        await database.execute(
            "INSERT OR IGNORE INTO tags (contentid, tag) VALUES(:contentid, :tag)",
            {"contentid": contentid, "tag": tag},
        )


def safe_parse(meta: str) -> Dict[str, Any]:
    # noinspection PyBroadException
    try:
        return orjson.loads(meta)
    except Exception:
        return {}


def get_lite_content_class(
    record: Record, include_meta: bool, parse_meta: bool, include_liked: bool = False
) -> LiteContent:
    """
    Populates a lite content object
    """
    # noinspection PyProtectedMember
    m = record._mapping
    return LiteContent(
        contentid=m["oid"],
        userid=m["userid"],
        username=m["username"],
        likes=m["likes"],
        tags=m["tags"].split(",") if m["tags"] else [],
        title=m["title"],
        version=m["version"],
        meta=(safe_parse(m["meta"]) if parse_meta else m["meta"])
        if include_meta
        else None,
        is_liked=bool(m["is_liked"]) if include_liked else None,
    )


def get_content_class(record: Record, parse_meta: bool = True) -> Content:
    """
    Populates a content object
    """
    # noinspection PyProtectedMember
    m = record._mapping
    return Content(
        contentid=m["oid"],
        userid=m["userid"],
        username=m["username"],
        likes=m["likes"],
        tags=m["tags"].split(",") if m["tags"] else [],
        title=m["title"],
        version=m["version"],
        meta=safe_parse(m["meta"]) if parse_meta else m["meta"],
        data=base64.b64encode(m["data"]).decode("utf-8"),
    )


def get_lite_user_class(record: Record):
    """
    Populates a user object
    """
    return LiteUser(
        userid=record["oid"],
        username=record["username"],
        submission_count=record["submission_count"],
        likes_given=record["likes_given"],
        likes_received=record["likes_received"],
        moderator=record["moderator"] > 0,
    )


async def get_user_class(
    userid: int,
    username: str,
    moderator: int,
    submissions: list[LiteContent],
    likes: list[LiteContent],
):
    """
    Populates a user object
    """
    likes_received = sum([int(c.likes) for c in submissions])
    return User(
        userid=userid,
        username=username,
        likes_received=likes_received,
        likes=likes,
        submissions=submissions,
        moderator=moderator > 0,
    )


async def fetch_content(
    contentid: int,
    parse_meta: bool = True,
    project: Optional[str] = None,
    include_hidden: bool = False,
) -> Content:
    prompt = get_base_select(True, True) + "WHERE c.oid = :contentid"
    values: dict[str, Any] = {"contentid": contentid}
    if project is not None:
        prompt += " AND c.project = :project"
        values["project"] = project
    if not include_hidden:
        prompt += " AND NOT users.banned"
        prompt += (
            " AND 1.0 + precomputation.likes / 10.0 "
            "- precomputation.reports >= 0.0"
        )

    content = await common.database.fetch_one(prompt, values)
    if content is None:
        raise HTTPException(404, "Content not found")
    return get_content_class(content, parse_meta)


async def logged_in_guard(
    authorization: Optional[str] = Header(None),
    session_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE),
):
    """
    Ensures the user is logged in.
    """
    userid = await token_to_userid(common.database, authorization, session_token)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    return userid


async def owner_guard(
    project: str = Path(...),
    contentid: int = Path(...),
    authorization: Optional[str] = Header(None),
    session_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE),
):
    """
    Ensures the user owns the content or is a moderator.
    """
    userid = await token_to_userid(common.database, authorization, session_token)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if not await owns_content(
        common.database, project, contentid, userid
    ) and not await is_moderator(common.database, userid):
        raise HTTPException(403, "Not allowed")

    return userid


async def moderator_guard(
    authorization: Optional[str] = Header(None),
    session_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE),
):
    """
    Ensures the user is a moderator.
    """
    userid = await token_to_userid(common.database, authorization, session_token)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if not await is_moderator(common.database, userid):
        raise HTTPException(403, "Not a moderator")

    return userid
