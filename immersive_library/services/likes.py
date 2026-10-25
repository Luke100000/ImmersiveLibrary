from immersive_library.database import database
from immersive_library.utils import content_guard, update_precomputation


async def set_like(project: str, content_id: int, user_id: int, liked: bool) -> bool:
    async with database.transaction():
        if liked:
            statement = """
                INSERT INTO likes (user_id, content_id)
                SELECT :user_id, :content_id FROM content WHERE oid=:content_id AND project=:project
                ON CONFLICT (user_id, content_id) DO NOTHING RETURNING user_id
            """
        else:
            statement = """
                DELETE FROM likes WHERE user_id=:user_id AND content_id=:content_id
                AND EXISTS (SELECT 1 FROM content WHERE oid=:content_id AND project=:project)
                RETURNING user_id
            """
        changed = (
            await database.fetch_val(
                statement,
                {"user_id": user_id, "content_id": content_id, "project": project},
            )
            is not None
        )
        await content_guard(project, content_id)
        if changed:
            await update_precomputation(database, content_id)
    return changed
