import hashlib
import json
from typing import Any

from databases import Database
from databases.interfaces import Record
from fastapi import Header, HTTPException, Path

from immersive_library.database import database as app_database
from immersive_library.models import LiteUser

MAX_USER_TOKENS = 10


async def update_precomputation(
    database: Database, content_id: int | None = None
) -> None:
    """
    Refreshes the database persistent cache
    :param database: The database to refresh
    :param content_id: The content_id to refresh, or None to refresh all
    """
    await database.execute(
        f"""
        INSERT OR REPLACE
        INTO precomputation (content_id, tags, likes, reports)
        SELECT content.oid,
               COALESCE(tagged_content.c_tags, '') as tags,
               COALESCE(liked_content.c_likes, 0) as likes,
               COALESCE(reported_c.reports, 0) as reports
        FROM content

         LEFT JOIN (SELECT likes.content_id, COUNT(*) as c_likes
                    FROM likes
                    {"" if content_id is None else "WHERE likes.content_id = :content_id"}
                    GROUP BY likes.content_id) liked_content ON liked_content.content_id = content.oid

         LEFT JOIN (SELECT tags.content_id, GROUP_CONCAT(tag, ',' ORDER BY rowid) as c_tags
                    FROM tags
                    {"" if content_id is None else "WHERE tags.content_id = :content_id"}
                    GROUP BY tags.content_id) tagged_content on tagged_content.content_id = content.oid

         LEFT JOIN (SELECT reports.content_id, COUNT(*) as reports
                    FROM reports
                    WHERE reports.reason = 'DEFAULT'
                    {"" if content_id is None else "AND reports.content_id = :content_id"}
                    GROUP BY reports.content_id) reported_c on reported_c.content_id = content.oid

        {"" if content_id is None else "WHERE content.oid = :content_id"}
    """,
        {} if content_id is None else {"content_id": content_id},
    )


def sha256(string: str) -> str:
    return hashlib.sha256(string.encode("utf-8")).hexdigest()


async def token_to_user_id(
    database: Database, token: str | None = None, authorization: str = Header(None)
) -> int | None:
    """
    Return the user_id for a given token, or None if the token is invalid
    """
    if authorization is not None and authorization.startswith("Bearer "):
        token = sha256(authorization[7:])
    if not token:
        return None
    user_id = await database.fetch_one(
        "SELECT user_id FROM user_tokens WHERE token=:token", {"token": token}
    )
    return None if user_id is None else user_id[0]


async def get_count(database: Database, query: str, params: dict[str, Any]) -> int:
    row = await database.fetch_one(query, params)
    return row[0] if row is not None else 0


async def exists(database: Database, query: str, params: dict[str, Any]) -> bool:
    return await get_count(database, query, params) > 0


async def user_exists(database: Database, user_id: int) -> bool:
    """
    Checks if the user with the given user_id exists
    """
    return await exists(
        database, "SELECT count(*) FROM users WHERE oid=:user_id", {"user_id": user_id}
    )


async def login_user(
    database: Database, google_user_id: str, username: str, token: str
) -> None:
    """
    Logs in the user, creating an account if necessary and updating username and token
    """
    async with database.transaction():
        # Create user
        await database.execute(
            """
            INSERT INTO users (google_user_id, username, moderator, banned)
            VALUES (:google_user_id, :username, FALSE, FALSE)
            ON CONFLICT (google_user_id) DO UPDATE SET username=:username
            """,
            {"google_user_id": google_user_id, "username": username},
        )
        user = await database.fetch_one(
            "SELECT oid FROM users WHERE google_user_id=:google_user_id",
            {"google_user_id": google_user_id},
        )
        user_id = user["oid"]

        # Invalidate token
        await database.execute(
            "DELETE FROM user_tokens WHERE token=:token",
            {"token": token},
        )

        # Insert new token
        await database.execute(
            "INSERT INTO user_tokens (token, user_id) VALUES (:token, :user_id)",
            {"token": token, "user_id": user_id},
        )

        # Drop old tokens
        await database.execute(
            """
            DELETE FROM user_tokens
            WHERE user_id=:user_id AND oid NOT IN (
                SELECT oid
                FROM user_tokens
                WHERE user_id=:user_id
                ORDER BY oid DESC
                LIMIT :max_tokens
            )
            """,
            {"user_id": user_id, "max_tokens": MAX_USER_TOKENS},
        )


async def owns_content(database: Database, content_id: int, user_id: int) -> bool:
    """
    Checks if the user owns that content
    """
    return await exists(
        database,
        "SELECT count(*) FROM content WHERE user_id=:user_id AND oid=:content_id",
        {"user_id": user_id, "content_id": content_id},
    )


async def is_moderator(database: Database, user_id: int) -> bool:
    """
    Checks if the user is a moderator
    """
    return await exists(
        database,
        "SELECT count(*) FROM users WHERE oid=:user_id AND moderator=TRUE",
        {"user_id": user_id},
    )


async def is_banned(database: Database, user_id: int) -> bool:
    """
    Checks if the user is banned
    """
    return await exists(
        database,
        "SELECT count(*) FROM users WHERE oid=:user_id AND banned=TRUE",
        {"user_id": user_id},
    )


async def set_moderator(database: Database, user_id: int, moderator: bool) -> None:
    """
    Sets moderator status
    """
    await database.execute(
        "UPDATE users SET moderator=:moderator WHERE oid=:user_id",
        {"moderator": moderator, "user_id": user_id},
    )


async def set_banned(database: Database, user_id: int, banned: bool) -> None:
    """
    Sets banned status
    """
    await database.execute(
        "UPDATE users SET banned=:banned WHERE oid=:user_id",
        {"banned": banned, "user_id": user_id},
    )


async def has_tag(database: Database, content_id: int, tag: str) -> bool:
    """
    Checks if the given content has a given tag
    """
    return await exists(
        database,
        "SELECT count(*) FROM tags WHERE tag=:tag AND content_id=:content_id",
        {"tag": tag, "content_id": content_id},
    )


async def set_tags(database: Database, content_id: int, tags: list[str]) -> None:
    """
    Replaces the tags for a given content
    """
    # Keep unchanged tags so their creation times survive content updates.
    await database.execute(
        "DELETE FROM tags WHERE content_id=:content_id "
        "AND tag NOT IN (SELECT value FROM json_each(:tags))",
        {"content_id": content_id, "tags": json.dumps(tags)},
    )

    for tag in tags:
        await database.execute(
            """
            INSERT INTO tags (content_id, tag) VALUES(:content_id, :tag)
            ON CONFLICT (content_id, tag) DO NOTHING
            """,
            {"content_id": content_id, "tag": tag},
        )


def get_lite_user_class(record: Record) -> LiteUser:
    """
    Populates a user object
    """
    return LiteUser(
        user_id=record["oid"],
        username=record["username"],
        submission_count=record["submission_count"],
        likes_given=record["likes_given"],
        likes_received=record["likes_received"],
        moderator=record["moderator"] > 0,
    )


async def content_guard(project: str, content_id: int) -> None:
    if not await app_database.fetch_val(
        "SELECT 1 FROM content WHERE oid=:content_id AND project=:project",
        {"content_id": content_id, "project": project},
    ):
        raise HTTPException(404, "Content not found")


async def logged_in_guard(
    token: str | None = None, authorization: str = Header(None)
) -> int:
    """
    Ensures the user is logged in.
    """
    user_id = await token_to_user_id(app_database, token, authorization)

    if user_id is None:
        raise HTTPException(401, "Token invalid")

    if await is_banned(app_database, user_id):
        raise HTTPException(403, "User is banned")

    return user_id


async def owner_guard(
    project: str,
    content_id: int = Path(...),
    token: str | None = None,
    authorization: str = Header(None),
) -> int:
    """
    Ensures the user owns the content or is a moderator.
    """
    user_id = await logged_in_guard(token, authorization)
    await content_guard(project, content_id)

    if not await owns_content(
        app_database, content_id, user_id
    ) and not await is_moderator(app_database, user_id):
        raise HTTPException(403, "Not allowed")

    return user_id


async def moderator_guard(
    token: str | None = None, authorization: str = Header(None)
) -> int:
    """
    Ensures the user is a moderator.
    """
    user_id = await logged_in_guard(token, authorization)

    if not await is_moderator(app_database, user_id):
        raise HTTPException(403, "Not a moderator")

    return user_id
