from fastapi import APIRouter

from immersive_library.common import database
from immersive_library.routers.tag import list_project_tags

router = APIRouter()


@router.get("/v1/stats/{project}")
async def get_statistics(project: str):
    content_count = await database.fetch_one("SELECT count(*) from content")
    content_count_liked = await database.fetch_one(
        """
        SELECT count(*)
        FROM content
        INNER JOIN precomputation ON content.oid = precomputation.contentid
        WHERE precomputation.likes > 10 AND content.project = :project
    """,
        {"project": project},
    )
    users_count = await database.fetch_one("SELECT count(*) FROM users")
    users_banned_count = await database.fetch_one(
        "SELECT count(*) FROM users WHERE banned > 0"
    )
    likes_count = await database.fetch_one("SELECT count(*) FROM likes")
    reports_count = await database.fetch_one("SELECT count(*) FROM reports")

    tags = dict(await list_project_tags(project, limit=100, offset=0))

    random_oid = await database.fetch_one(
        """
        SELECT oid
        FROM (
            SELECT content.oid
            FROM content
            INNER JOIN precomputation ON content.oid = precomputation.contentid
            WHERE precomputation.likes > 100 AND content.project = :project
            ORDER BY RANDOM()
            LIMIT 1
        );
    """,
        {"project": project},
    )

    return {
        "oid": random_oid[0],
        "top_tags": ", ".join(list(tags["tags"].keys())[:30]),
        "content": "{:,}".format(content_count[0]),
        "content_liked": "{:,}".format(content_count_liked[0]),
        "users": "{:,}".format(users_count[0]),
        "users_banned_count": "{:,}".format(users_banned_count[0]),
        "likes": "{:,}".format(likes_count[0]),
        "reports": "{:,}".format(reports_count[0]),
    }
