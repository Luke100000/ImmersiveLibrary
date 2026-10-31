from databases.interfaces import Record

from immersive_library.database import database
from immersive_library.enums import Inclusion, UserOrder
from immersive_library.services.reports import REPORT_SCORE


async def list_users(
    project: str,
    user_id: int | None = None,
    q: str | None = None,
    banned: Inclusion = Inclusion.EXCLUDE,
    order: UserOrder = UserOrder.DATE,
    descending: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[Record]:
    values = {"limit": limit, "offset": offset, "project": project}
    user_filter = ""
    if user_id is not None:
        user_filter = "AND users.oid = :user_id"
        values["user_id"] = user_id
    elif banned == Inclusion.EXCLUDE:
        user_filter = "AND NOT users.banned"
    elif banned == Inclusion.ONLY:
        user_filter = "AND users.banned"
    if q and q.strip():
        user_filter += " AND users.username LIKE :q"
        values["q"] = f"%{q.strip()}%"

    direction = "DESC" if descending else "ASC"
    sort_column = {
        UserOrder.DATE: "users.oid",
        UserOrder.SUBMISSION_COUNT: "submission_count",
        UserOrder.LIKES_GIVEN: "likes_given",
        UserOrder.LIKES_RECEIVED: "likes_received",
        UserOrder.RECENT_LIKES_RECEIVED: "recent_likes_received",
        UserOrder.REPORT_SCORE: "average_report_score",
    }[order]
    ordering = f"{sort_column} {direction}"
    if order != UserOrder.DATE:
        ordering += f", users.oid {direction}"

    # Statistics-based ordering needs all users' totals before pagination.
    page_first = user_id is not None or order == UserOrder.DATE

    return await database.fetch_all(
        f"""
            WITH selected_users AS (
                SELECT oid, username, moderator, banned
                FROM users
                WHERE true
                {user_filter}
                {f"ORDER BY oid {direction} LIMIT :limit OFFSET :offset" if page_first else ""}
            )
            SELECT users.oid,
                   users.username,
                   users.moderator,
                   users.banned,
                   COALESCE(submitted_content.submission_count, 0) as submission_count,
                   COALESCE(likes_given.count, 0) as likes_given,
                   COALESCE(submitted_content.likes_received, 0) as likes_received,
                   COALESCE(submitted_content.recent_likes_received, 0) as recent_likes_received,
                   COALESCE(submitted_content.average_report_score, 0) as average_report_score
            FROM selected_users users

            LEFT JOIN (
                SELECT content.user_id,
                       COUNT(*) as submission_count,
                       SUM(COALESCE(precomputation.likes, 0)) as likes_received,
                       SUM(COALESCE(precomputation.recent_likes, 0)) as recent_likes_received,
                       AVG(COALESCE({REPORT_SCORE}, 0)) as average_report_score
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
