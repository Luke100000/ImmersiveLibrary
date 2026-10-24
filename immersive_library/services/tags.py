from immersive_library.database import database
from immersive_library.models import TagDictSuccess


async def list_project_tags(
    project: str, limit: int = 100, offset: int = 0
) -> TagDictSuccess:
    rows = await database.fetch_all(
        """
        SELECT tag, COUNT(*) as count
        FROM tags
        INNER JOIN content ON tags.contentid = content.oid
        WHERE content.project = :project
        GROUP BY tag
        ORDER BY count DESC
        LIMIT :limit
        OFFSET :offset
        """,
        {"project": project, "limit": limit, "offset": offset},
    )

    return TagDictSuccess(tags={row["tag"]: row["count"] for row in rows})
