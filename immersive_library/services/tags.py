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
        INNER JOIN content ON tags.content_id = content.oid
        WHERE content.project = :project
        GROUP BY tag
        ORDER BY count DESC, tag ASC
        LIMIT :limit OFFSET :offset
        """,
        {"project": project, "limit": limit, "offset": offset},
    )


async def set_tag(project: str, content_id: int, tag: str, tagged: bool) -> bool:
    async with database.transaction():
        if tagged:
            statement = """
                INSERT INTO tags (content_id, tag)
                SELECT :content_id, :tag FROM content WHERE oid=:content_id AND project=:project
                ON CONFLICT (content_id, tag) DO NOTHING RETURNING tag
            """
        else:
            statement = """
                DELETE FROM tags WHERE content_id=:content_id AND tag=:tag
                AND EXISTS (SELECT 1 FROM content WHERE oid=:content_id AND project=:project)
                RETURNING tag
            """

        changed = (
            await database.fetch_val(
                statement, {"content_id": content_id, "tag": tag, "project": project}
            )
            is not None
        )

        await content_guard(project, content_id)

        if changed:
            await update_precomputation(database, content_id)

    return changed
