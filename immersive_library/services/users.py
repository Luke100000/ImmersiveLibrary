from enum import Enum

from databases.interfaces import Record

from immersive_library.database import database


class UserOrder(str, Enum):
    OID = "date"
    SUBMISSION_COUNT = "submissions"
    LIKES_GIVEN = "likes_given"
    LIKES_RECEIVED = "likes_received"


async def list_users(
    project: str,
    limit: int,
    offset: int,
    order: UserOrder,
    descending: bool,
    userid: int | None = None,
) -> list[Record]:
    values = {"limit": limit, "offset": offset, "project": project}
    user_filter = ""
    if userid is not None:
        user_filter = "AND users.oid = :userid"
        values["userid"] = userid

    return await database.fetch_all(
        f"""
            SELECT users.oid,
                   users.username,
                   users.moderator,
                   COALESCE(submitted_content.submission_count, 0) as submission_count,
                   COALESCE(likes_given.count, 0) as likes_given,
                   COALESCE(likes_received.count, 0) as likes_received
            FROM users

            LEFT JOIN (
                SELECT content.userid, COUNT(content.oid) as submission_count
                FROM content
                WHERE content.project = :project
                GROUP BY content.userid
            ) submitted_content ON submitted_content.userid = users.oid

            LEFT JOIN (
                SELECT likes.userid, COUNT(likes.oid) as count
                FROM likes
                GROUP BY likes.userid
            ) likes_given ON likes_given.userid = users.oid

            LEFT JOIN (
                SELECT c2.userid, SUM(COALESCE(precomputation.likes, 0)) as count
                FROM content c2
                LEFT JOIN precomputation ON precomputation.contentid = c2.oid
                WHERE c2.project = :project
                GROUP BY c2.userid
            ) likes_received ON likes_received.userid = users.oid

            WHERE users.banned = 0
            {user_filter}

            ORDER BY {order.name} {"DESC" if descending else "ASC"}
            LIMIT :limit
            OFFSET :offset
        """,
        values,
    )
