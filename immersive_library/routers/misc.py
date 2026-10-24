from fastapi import APIRouter
from fastapi_cache.decorator import cache

from immersive_library.caching import public_cache
from immersive_library.common import database
from immersive_library.routers.tag import list_project_tags

router = APIRouter()


@router.get("/v1/stats/{project}")
@public_cache()
@cache(expire=60)
async def get_statistics(project: str) -> dict[str, str | int]:
    content_count = await database.fetch_val(
        "SELECT count(*) from content WHERE project = :project", {"project": project}
    )
    content_count_liked = await database.fetch_val(
        """
        SELECT count(*)
        FROM content
        INNER JOIN precomputation ON content.oid = precomputation.contentid
        WHERE precomputation.likes > 10 AND content.project = :project
    """,
        {"project": project},
    )
    users_count = await database.fetch_val("SELECT count(*) FROM users")
    users_banned_count = await database.fetch_val(
        "SELECT count(*) FROM users WHERE banned > 0"
    )
    likes_count = await database.fetch_val("SELECT count(*) FROM likes")
    reports_count = await database.fetch_val("SELECT count(*) FROM reports")

    tags = await list_project_tags(project, limit=50, offset=0)

    random_oid = await database.fetch_val(
        """
        SELECT oid
        FROM (
            SELECT content.oid
            FROM content
            INNER JOIN precomputation ON content.oid = precomputation.contentid
            WHERE precomputation.likes > 10 AND content.project = :project
            ORDER BY RANDOM()
            LIMIT 1
        );
    """,
        {"project": project},
    )

    return {
        "oid": -1 if random_oid is None else random_oid,
        "top_tags": ", ".join(list(tags.tags)[:30]),
        "content": f"{content_count:,}",
        "content_liked": f"{content_count_liked:,}",
        "users": f"{users_count:,}",
        "users_banned_count": f"{users_banned_count:,}",
        "likes": f"{likes_count:,}",
        "reports": f"{reports_count:,}",
    }
