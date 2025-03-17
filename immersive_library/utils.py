import base64
import hashlib
from typing import List, Optional, Any, Dict

import orjson
from cachetools import cached, TTLCache
from cachetools.keys import hashkey
from cachetools_async import cached as cached_async
from databases import Database
from databases.interfaces import Record
from fastapi import Header

from immersive_library.api_types import (
    Content,
    User,
    LiteContent,
    LiteUser,
)


async def refresh_precomputation(database: Database):
    """
    Refreshes the database persistent cache
    :param database: The database to refresh
    """
    await database.execute(
        """
        INSERT OR REPLACE
        INTO precomputation (contentid, dirty, tags, likes, reports, counter_reports)
        SELECT temp.oid,
               0,
               CASE WHEN tagged_content.c_tags is NULL THEN '' ELSE tagged_content.c_tags END as tags,
               CASE WHEN liked_content.c_likes is NULL THEN 0 ELSE liked_content.c_likes END  as likes,
               CASE WHEN reported_c.reports is NULL THEN 0 ELSE reported_c.reports END        as reports,
               CASE WHEN countered_c.reports is NULL THEN 0 ELSE countered_c.reports END      as counter_reports
        FROM (SELECT content.oid
              FROM content
                       LEFT JOIN precomputation
                                 ON content.oid = precomputation.contentid
              WHERE precomputation.dirty IS NOT 0) as temp
        
        
                 LEFT JOIN (SELECT likes.contentid, COUNT(*) as c_likes
                            FROM likes
                            GROUP BY likes.contentid) liked_content ON liked_content.contentid = temp.oid
        
                 LEFT JOIN (SELECT tags.contentid, GROUP_CONCAT(tag, ',') as c_tags
                            FROM tags
                            GROUP BY tags.contentid) tagged_content on tagged_content.contentid = temp.oid
        
                 LEFT JOIN (SELECT reports.contentid, COUNT(*) as reports
                            FROM reports
                            WHERE reports.reason = 'DEFAULT'
                            GROUP BY reports.contentid) reported_c on reported_c.contentid = temp.oid
        
                 LEFT JOIN (SELECT reports.contentid, COUNT(*) as reports
                            FROM reports
                            WHERE reports.reason = 'COUNTER_DEFAULT'
                            GROUP BY reports.contentid) countered_c on countered_c.contentid = temp.oid
    """
    )


@cached_async(
    TTLCache(maxsize=10000, ttl=1800), key=lambda database, project: hashkey(project)
)
async def refresh_user_precomputation(database: Database, project: str):
    """
    Refreshes the user precomputation cache for a given project.
    """
    await database.execute(
        """
        INSERT OR REPLACE
        INTO precomputation_users (userid, project, submission_count, likes_given, likes_received)
        SELECT
            users.oid as userid,
            :project,
            COALESCE(submissions.submission_count, 0) as submission_count,
            COALESCE(submissions.likes_received, 0) as likes_received,
            COALESCE(likes_given_counts.likes_given, 0) as likes_given
        FROM
            users
        LEFT JOIN (
            SELECT
                content.userid,
                COUNT(content.oid) as submission_count,
                SUM(COALESCE(precomputation.likes, 0)) as likes_received
            FROM
                content
            LEFT JOIN
                precomputation ON precomputation.contentid = content.oid
            WHERE
                content.project = :project
            GROUP BY
                content.userid
        ) submissions ON submissions.userid = users.oid
        
        LEFT JOIN (
            SELECT
                likes.userid,
                COUNT(likes.oid) as likes_given
            FROM
                likes
            LEFT JOIN
                content ON likes.contentid = content.oid
            WHERE
                content.project = :project
            GROUP BY
                likes.userid
        ) likes_given_counts ON likes_given_counts.userid = users.oid
        
        WHERE
            COALESCE(submissions.submission_count, 0) > 0
            OR COALESCE(submissions.likes_received, 0) > 0
            OR COALESCE(likes_given_counts.likes_given, 0) > 0;

    """,
        {"project": project},
    )


async def set_dirty(database: Database, contentid: int):
    """
    Marks this content as dirty, recomputing the cached content once required
    :param database: The database
    :param contentid: The content id to mark as dirty
    """
    if contentid > 0:
        await database.execute(
            """
        UPDATE precomputation
        SET dirty = 1
        WHERE contentid = :contentid    
        """,
            {"contentid": contentid},
        )

    await refresh_precomputation(database)


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
    Logins the user, creating an account of necessary and updating username and token
    """
    # Invalidate same tokens, the token has to be unique
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


async def has_reported(database: Database, userid: int, contentid: int, reason: str):
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


async def get_username(database: Database, userid: int) -> Optional[str]:
    """
    Retrieves the username of a user
    """
    username = await database.fetch_one(
        "SELECT username FROM users WHERE oid=:userid", {"userid": userid}
    )
    return None if username is None else username[0]


async def get_likes(database: Database, contentid: int) -> int:
    """
    Retrieves the total likes a content received
    """
    return await get_count(
        database,
        "SELECT COUNT(*) FROM likes WHERE contentid=:contentid",
        {"contentid": contentid},
    )


async def get_tags(database: Database, contentid: int) -> List[str]:
    """
    Get all tags for a given content
    """
    tags = await database.fetch_all(
        "SELECT tag FROM tags WHERE contentid=:contentid", {"contentid": contentid}
    )
    return [t[0] for t in tags]


async def get_project_tags(
    database: Database, project: str, k: int = 100, offset: int = 0
) -> Dict[str, int]:
    """
    Retrieves the top k most common tags of a project.
    """
    rows = await database.fetch_all(
        """
        SELECT tag, COUNT(*) as count
        FROM tags
        INNER JOIN content ON tags.contentid = content.oid
        WHERE content.project = :project
        GROUP BY tag
        ORDER BY count DESC
        LIMIT :k
        OFFSET :offset
        """,
        {"project": project, "k": k, "offset": offset},
    )

    return {row["tag"]: row["count"] for row in rows}


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
