from immersive_library.common import get_project
from immersive_library.database import database
from immersive_library.utils import content_guard, update_precomputation


async def set_report(
    project: str, content_id: int, user_id: int, reason: str, reported: bool
) -> bool:
    await content_guard(project, content_id)

    if reported:
        await get_project(project).validate(
            "pre_report", database, user_id, content_id, reason
        )

    async with database.transaction():
        if reported:
            statement = """
                INSERT INTO reports (user_id, content_id, reason)
                SELECT :user_id, :content_id, :reason FROM content WHERE oid=:content_id AND project=:project
                ON CONFLICT (user_id, content_id, reason) DO NOTHING RETURNING user_id
            """
        else:
            statement = """
                DELETE FROM reports WHERE user_id=:user_id AND content_id=:content_id AND reason=:reason
                AND EXISTS (SELECT 1 FROM content WHERE oid=:content_id AND project=:project)
                RETURNING user_id
            """

        changed = (
            await database.fetch_val(
                statement,
                {
                    "user_id": user_id,
                    "content_id": content_id,
                    "reason": reason,
                    "project": project,
                },
            )
            is not None
        )

        await content_guard(project, content_id)

        if changed:
            if reported:
                await get_project(project).call(
                    "post_report", database, user_id, content_id, reason
                )
            await update_precomputation(database, content_id)

    return changed
