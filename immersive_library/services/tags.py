from databases.interfaces import Record

from immersive_library.database import database
from immersive_library.utils import content_guard, update_precomputation


async def list_project_tags(
    project: str, limit: int = 100, offset: int = 0
) -> list[Record]:
    return await database.fetch_all(
        """
        SELECT tag, COUNT(*) as count
        FROM tags
        INNER JOIN content ON tags.contentid = content.oid
        WHERE content.project = :project
        GROUP BY tag
        ORDER BY count DESC, tag ASC
        LIMIT :limit OFFSET :offset
        """,
        {"project": project, "limit": limit, "offset": offset},
    )


async def set_tag(project: str, contentid: int, tag: str, tagged: bool) -> bool:
    async with database.transaction():
        if tagged:
            statement = """
                INSERT INTO tags (contentid, tag)
                SELECT :contentid, :tag FROM content WHERE oid=:contentid AND project=:project
                ON CONFLICT (contentid, tag) DO NOTHING RETURNING tag
            """
        else:
            statement = """
                DELETE FROM tags WHERE contentid=:contentid AND tag=:tag
                AND EXISTS (SELECT 1 FROM content WHERE oid=:contentid AND project=:project)
                RETURNING tag
            """

        changed = (
            await database.fetch_val(
                statement, {"contentid": contentid, "tag": tag, "project": project}
            )
            is not None
        )

        await content_guard(project, contentid)

        if changed:
            await update_precomputation(database, contentid)

    return changed
