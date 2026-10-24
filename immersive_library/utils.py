import base64
import hashlib
from typing import Any

import orjson
from cachetools import cached
from databases import Database
from databases.interfaces import Record
from fastapi import Header, HTTPException, Path

from immersive_library.database import database as app_database
from immersive_library.models import (
    Content,
    LiteContent,
    LiteUser,
)

MAX_USER_TOKENS = 10


async def update_precomputation(
    database: Database, contentid: int | None = None
) -> None:
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
def get_base_select(include_data: bool, include_meta: bool) -> str:
    query = """
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

    if not include_meta:
        query = query.replace("c.meta,", "")

    if not include_data:
        query = query.replace("c.data,", "")

    return query


def sha256(string: str) -> str:
    return hashlib.sha256(string.encode("utf-8")).hexdigest()


async def token_to_userid(
    database: Database, token: str | None = None, authorization: str = Header(None)
) -> int | None:
    """
    Return the userid for a given token, or None if the token is invalid
    """
    if authorization is not None and str(authorization).startswith("Bearer "):
        token = sha256(authorization[7:])
    if not token:
        return None
    userid = await database.fetch_one(
        "SELECT userid FROM user_tokens WHERE token=:token", {"token": token}
    )
    return None if userid is None else userid[0]


async def get_count(database: Database, query: str, params: dict[str, Any]) -> int:
    row = await database.fetch_one(query, params)
    return row[0] if row is not None else 0


async def exists(database: Database, query: str, params: dict[str, Any]) -> bool:
    return await get_count(database, query, params) > 0


async def user_exists(database: Database, userid: int) -> bool:
    """
    Checks if the user with the given userid exists
    """
    return await exists(
        database, "SELECT count(*) FROM users WHERE oid=:userid", {"userid": userid}
    )


async def login_user(
    database: Database, google_userid: str, username: str, token: str
) -> None:
    """
    Logs in the user, creating an account if necessary and updating username and token
    """
    async with database.transaction():
        # Create user
        await database.execute(
            """
            INSERT INTO users (google_userid, username, moderator, banned)
            VALUES (:google_userid, :username, FALSE, FALSE)
            ON CONFLICT (google_userid) DO UPDATE SET username=:username
            """,
            {"google_userid": google_userid, "username": username},
        )
        user = await database.fetch_one(
            "SELECT oid FROM users WHERE google_userid=:google_userid",
            {"google_userid": google_userid},
        )
        userid = user["oid"]

        # Invalidate token
        await database.execute(
            "DELETE FROM user_tokens WHERE token=:token",
            {"token": token},
        )

        # Insert new token
        await database.execute(
            "INSERT INTO user_tokens (token, userid) VALUES (:token, :userid)",
            {"token": token, "userid": userid},
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


async def owns_content(database: Database, contentid: int, userid: int) -> bool:
    """
    Checks if the user owns that content
    """
    return await exists(
        database,
        "SELECT count(*) FROM content WHERE userid=:userid AND oid=:contentid",
        {"userid": userid, "contentid": contentid},
    )


async def is_moderator(database: Database, userid: int) -> bool:
    """
    Checks if the user is a moderator
    """
    return await exists(
        database,
        "SELECT count(*) FROM users WHERE oid=:userid AND moderator=TRUE",
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


async def set_moderator(database: Database, userid: int, moderator: bool) -> None:
    """
    Sets moderator status
    """
    await database.execute(
        "UPDATE users SET moderator=:moderator WHERE oid=:userid",
        {"moderator": moderator, "userid": userid},
    )


async def set_banned(database: Database, userid: int, banned: bool) -> None:
    """
    Sets banned status
    """
    await database.execute(
        "UPDATE users SET banned=:banned WHERE oid=:userid",
        {"banned": banned, "userid": userid},
    )


async def has_liked(database: Database, userid: int, contentid: int) -> bool:
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
) -> bool:
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


async def set_tags(database: Database, contentid: int, tags: list[str]) -> None:
    """
    Replaces the tags for a given content
    """
    await database.execute(
        "DELETE FROM tags WHERE contentid=:contentid",
        {"contentid": contentid},
    )

    for tag in tags:
        await database.execute(
            """
            INSERT INTO tags (contentid, tag) VALUES(:contentid, :tag)
            ON CONFLICT (contentid, tag) DO NOTHING
            """,
            {"contentid": contentid, "tag": tag},
        )


def safe_parse(meta: str) -> dict[str, Any]:
    try:
        parsed_meta = orjson.loads(meta)
    except orjson.JSONDecodeError:
        return {}

    return parsed_meta if isinstance(parsed_meta, dict) else {}


def get_lite_content_class(
    record: Record, include_meta: bool, parse_meta: bool
) -> LiteContent:
    """
    Populates a lite content object
    """
    meta = None
    if include_meta:
        meta = safe_parse(record["meta"]) if parse_meta else record["meta"]

    return LiteContent(
        contentid=record["oid"],
        userid=record["userid"],
        username=record["username"],
        likes=record["likes"],
        tags=record["tags"].split(",") if record["tags"] else [],
        title=record["title"],
        version=record["version"],
        meta=meta,
    )


def get_content_class(record: Record, parse_meta: bool = True) -> Content:
    """
    Populates a content object
    """
    return Content(
        contentid=record["oid"],
        userid=record["userid"],
        username=record["username"],
        likes=record["likes"],
        tags=record["tags"].split(",") if record["tags"] else [],
        title=record["title"],
        version=record["version"],
        meta=safe_parse(record["meta"]) if parse_meta else record["meta"],
        data=base64.b64encode(record["data"]).decode("utf-8"),
    )


def get_lite_user_class(record: Record) -> LiteUser:
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


async def content_guard(project: str, contentid: int) -> None:
    if not await app_database.fetch_val(
        "SELECT 1 FROM content WHERE oid=:contentid AND project=:project",
        {"contentid": contentid, "project": project},
    ):
        raise HTTPException(404, "Content not found")


async def fetch_content(
    project: str, contentid: int, parse_meta: bool = True
) -> Content:
    content = await app_database.fetch_one(
        get_base_select(True, True)
        + "WHERE c.oid = :contentid AND c.project = :project",
        {"contentid": contentid, "project": project},
    )

    if content is None:
        raise HTTPException(404, "Content not found")

    return get_content_class(content, parse_meta)


async def logged_in_guard(
    token: str | None = None, authorization: str = Header(None)
) -> int:
    """
    Ensures the user is logged in.
    """
    userid = await token_to_userid(app_database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if await is_banned(app_database, userid):
        raise HTTPException(403, "User is banned")

    return userid


async def owner_guard(
    project: str,
    contentid: int = Path(...),
    token: str | None = None,
    authorization: str = Header(None),
) -> int:
    """
    Ensures the user owns the content or is a moderator.
    """
    userid = await logged_in_guard(token, authorization)
    await content_guard(project, contentid)

    if not await owns_content(
        app_database, contentid, userid
    ) and not await is_moderator(app_database, userid):
        raise HTTPException(403, "Not allowed")

    return userid


async def moderator_guard(
    token: str | None = None, authorization: str = Header(None)
) -> int:
    """
    Ensures the user is a moderator.
    """
    userid = await logged_in_guard(token, authorization)

    if not await is_moderator(app_database, userid):
        raise HTTPException(403, "Not a moderator")

    return userid
