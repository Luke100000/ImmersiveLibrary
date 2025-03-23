from fastapi import APIRouter

from immersive_library.common import database

router = APIRouter()


@router.get("/v1/stats")
async def get_statistics():
    content_count = await database.fetch_one("SELECT count(*) from content")
    content_count_liked = await database.fetch_one(
        """
        SELECT count(*)
        FROM content
        INNER JOIN precomputation ON content.oid = precomputation.contentid
        WHERE precomputation.likes > 10
    """
    )
    users_count = await database.fetch_one("SELECT count(*) FROM users")
    users_banned_count = await database.fetch_one(
        "SELECT count(*) FROM users WHERE banned > 0"
    )
    likes_count = await database.fetch_one("SELECT count(*) FROM likes")
    reports_count = await database.fetch_one("SELECT count(*) FROM reports")

    top_tags = await database.fetch_all("""
        SELECT tag
        FROM tags
        GROUP BY tag
        HAVING count(*) > 10
        ORDER BY count(*) desc
        LIMIT 33
    """)

    random_oid = await database.fetch_one(
        """
        SELECT oid
        FROM (
            SELECT content.oid
            FROM content
            INNER JOIN precomputation ON content.oid = precomputation.contentid
            WHERE precomputation.likes > 100
            ORDER BY RANDOM()
            LIMIT 1
        );
    """
    )

    return {
        "oid": random_oid[0],
        "top_tags": ", ".join([t[0] for t in top_tags[3:]]),
        "content": "{:,}".format(content_count[0]),
        "content_liked": "{:,}".format(content_count_liked[0]),
        "users": "{:,}".format(users_count[0]),
        "users_banned_count": "{:,}".format(users_banned_count[0]),
        "likes": "{:,}".format(likes_count[0]),
        "reports": "{:,}".format(reports_count[0]),
    }
