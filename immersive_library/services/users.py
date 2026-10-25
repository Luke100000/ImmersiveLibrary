from databases.interfaces import Record

from immersive_library.database import database
from immersive_library.enums import UserOrder


async def list_users(
    project: str,
    limit: int,
    offset: int,
    order: UserOrder,
    descending: bool,
    user_id: int | None = None,
) -> list[Record]:
    values = {"limit": limit, "offset": offset, "project": project}
    user_filter = ""
    if user_id is not None:
        user_filter = "AND users.oid = :user_id"
        values["user_id"] = user_id

    direction = "DESC" if descending else "ASC"
    ordering = f"{order.name} {direction}"
    if order != UserOrder.OID:
        ordering += f", users.oid {direction}"

    # Statistics-based ordering needs all users' totals before pagination.
    page_first = user_id is not None or order == UserOrder.OID

    return await database.fetch_all(
        f"""
            WITH selected_users AS (
                SELECT oid, username, moderator
                FROM users
                WHERE users.banned = 0
                {user_filter}
                {f"ORDER BY oid {direction} LIMIT :limit OFFSET :offset" if page_first else ""}
            )
            SELECT users.oid,
                   users.username,
                   users.moderator,
                   COALESCE(submitted_content.submission_count, 0) as submission_count,
                   COALESCE(likes_given.count, 0) as likes_given,
                   COALESCE(submitted_content.likes_received, 0) as likes_received
            FROM selected_users users

            LEFT JOIN (
                SELECT content.user_id,
                       COUNT(*) as submission_count,
                       SUM(COALESCE(precomputation.likes, 0)) as likes_received
                FROM content
                LEFT JOIN precomputation ON precomputation.content_id = content.oid
                WHERE content.project = :project
                {"AND content.user_id IN (SELECT oid FROM selected_users)" if page_first else ""}
                GROUP BY content.user_id
            ) submitted_content ON submitted_content.user_id = users.oid

            LEFT JOIN (
                SELECT likes.user_id, COUNT(*) as count
                FROM likes
                {"WHERE likes.user_id IN (SELECT oid FROM selected_users)" if page_first else ""}
                GROUP BY likes.user_id
            ) likes_given ON likes_given.user_id = users.oid

            ORDER BY {ordering}
            LIMIT :limit
            OFFSET {0 if page_first else ":offset"}
        """,
        values,
    )
