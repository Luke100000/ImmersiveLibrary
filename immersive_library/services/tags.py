from fastapi import HTTPException

from immersive_library.database import database
from immersive_library.models import TagDictSuccess
from immersive_library.utils import has_tag, update_precomputation


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


async def set_tag(contentid: int, tag: str, tagged: bool) -> bool:
    if tagged:
        if "," in tag:
            raise HTTPException(401, "Contains invalid characters")

        inserted_tag = await database.fetch_val(
            """
            INSERT INTO tags (contentid, tag) VALUES(:contentid, :tag)
            ON CONFLICT (contentid, tag) DO NOTHING RETURNING tag
            """,
            {"contentid": contentid, "tag": tag},
        )
        if inserted_tag is None:
            return False
    else:
        if not await has_tag(database, contentid, tag):
            return False

        await database.execute(
            "DELETE FROM tags WHERE contentid=:contentid AND tag=:tag",
            {"contentid": contentid, "tag": tag},
        )

    await update_precomputation(database, contentid)
    return True
