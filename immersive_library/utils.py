import base64
import hashlib
from typing import Optional, Any, Dict

import orjson
from cachetools import cached
from databases import Database
from databases.interfaces import Record
from fastapi import Header

from immersive_library.models import (
    Content,
    User,
    LiteContent,
    LiteUser,
)


async def update_precomputation(database: Database, contentid: Optional[int] = None):
    """
    Refreshes the database persistent cache
    :param database: The database to refresh
    :param contentid: The contentid to refresh, or None to refresh all
    """
    await database.execute(
        f"""
        INSERT OR REPLACE
        INTO precomputation (contentid, tags, likes, reports, counter_reports)
        SELECT content.oid,
               CASE WHEN tagged_content.c_tags is NULL THEN '' ELSE tagged_content.c_tags END as tags,
               CASE WHEN liked_content.c_likes is NULL THEN 0 ELSE liked_content.c_likes END  as likes,
               CASE WHEN reported_c.reports is NULL THEN 0 ELSE reported_c.reports END        as reports,
               CASE WHEN countered_c.reports is NULL THEN 0 ELSE countered_c.reports END      as counter_reports
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

         LEFT JOIN (SELECT reports.contentid, COUNT(*) as reports
                    FROM reports
                    WHERE reports.reason = 'COUNTER_DEFAULT'
                    GROUP BY reports.contentid) countered_c on countered_c.contentid = content.oid
                    
        {"" if contentid is None else "WHERE content.oid = :contentid"}
    """,
        {} if contentid is None else {"contentid": contentid},
    )


@cached(cache={})
def get_base_select(include_data: bool, include_meta: bool):
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
               precomputation.reports,
               precomputation.counter_reports
        FROM content c
            INNER JOIN users ON c.userid = users.oid
            INNER JOIN precomputation ON c.oid = precomputation.contentid
    """

    if not include_meta:
        prompt = prompt.replace("c.meta,", "")

    if not include_data:
        prompt = prompt.replace("c.data,", "")

    return prompt


def sha256(string: str) -> str:
    sha256_hash = hashlib.sha256()
    sha256_hash.update(string.encode("utf-8"))
    return sha256_hash.hexdigest()


async def token_to_userid(
    database: Database, token: Optional[str] = None, authorization: str = Header(None)
) -> Optional[int]:
    """
    Return the userid for a given token, or None if the token is invalid
    """
    if authorization is not None and str(authorization).startswith("Bearer "):
        token = sha256(authorization[7:])
    if token is None:
        return None
    if len(token) == 0:
        return None
    userid = await database.fetch_one(
        "SELECT oid FROM users WHERE token=:token", {"token": token}
    )
    return None if userid is None else userid[0]


async def get_count(database: Database, query: str, params: dict[str, Any]):
    row = await database.fetch_one(query, params)
    return row[0] if row is not None else 0


async def exists(database: Database, query: str, params: dict[str, Any]):
    return await get_count(database, query, params) > 0


async def account_exists(database: Database, google_userid: str) -> bool:
    """
    Checks if the account with the given google userid exists
    """
    return await exists(
        database,
        "SELECT count(*) FROM users WHERE google_userid=:google_userid",
        {"google_userid": google_userid},
    )


async def user_exists(database: Database, userid: int) -> bool:
    """
    Checks if the user with the given userid exists
    """
    return await exists(
        database, "SELECT count(*) FROM users WHERE oid=:userid", {"userid": userid}
    )


async def login_user(database: Database, google_userid, username, token):
    """
    Logs in the user, creating an account of necessary and updating username and token
    """
    # Invalidate the same tokens, the token has to be unique
    await database.execute(
        "UPDATE users SET token='' WHERE token=:token",
        {"token": token},
    )

    if await account_exists(database, google_userid):
        await database.execute(
            "UPDATE users SET username=:username, token=:token WHERE google_userid=:google_userid",
            {"username": username, "token": token, "google_userid": google_userid},
        )
    else:
        await database.execute(
            "INSERT INTO users (google_userid, token, username, moderator, banned) VALUES (:google_userid, :token, :username, FALSE, FALSE)",
            {"google_userid": google_userid, "token": token, "username": username},
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


async def set_moderator(database: Database, userid: int, moderator: bool):
    """
    Sets moderator status
    """
    await database.execute(
        "UPDATE users SET moderator=:moderator WHERE oid=:userid",
        {"moderator": moderator, "userid": userid},
    )


async def set_banned(database: Database, userid: int, banned: bool):
    """
    Sets banned status
    """
    await database.execute(
        "UPDATE users SET banned=:banned WHERE oid=:userid",
        {"banned": banned, "userid": userid},
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
    """
    Replaces the tags for a given content
    """
    await database.execute(
        "DELETE FROM tags WHERE contentid=:contentid",
        {"contentid": contentid},
    )

    for tag in tags:
        await database.execute(
            "INSERT INTO tags (contentid, tag) VALUES(:contentid, :tag)",
            {"contentid": contentid, "tag": tag},
        )


def get_lite_content_class(
    record: Record, include_meta: bool, parse_meta: bool
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
    )


def safe_parse(meta: str) -> Dict[str, Any]:
    # noinspection PyBroadException
    try:
        return orjson.loads(meta)
    except Exception:
        return {}


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
    likes_received = sum([c.likes for c in submissions])
    return User(
        userid=userid,
        username=username,
        likes_received=likes_received,
        likes=likes,
        submissions=submissions,
        moderator=moderator > 0,
    )
