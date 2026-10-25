from immersive_library.common import get_project
from immersive_library.database import database
from immersive_library.utils import content_guard, update_precomputation


async def set_report(
    project: str, contentid: int, userid: int, reason: str, reported: bool
) -> bool:
    await content_guard(project, contentid)

    if reported:
        await get_project(project).validate(
            "pre_report", database, userid, contentid, reason
        )

    async with database.transaction():
        if reported:
            statement = """
                INSERT INTO reports (userid, contentid, reason)
                SELECT :userid, :contentid, :reason FROM content WHERE oid=:contentid AND project=:project
                ON CONFLICT (userid, contentid, reason) DO NOTHING RETURNING userid
            """
        else:
            statement = """
                DELETE FROM reports WHERE userid=:userid AND contentid=:contentid AND reason=:reason
                AND EXISTS (SELECT 1 FROM content WHERE oid=:contentid AND project=:project)
                RETURNING userid
            """

        changed = (
            await database.fetch_val(
                statement,
                {
                    "userid": userid,
                    "contentid": contentid,
                    "reason": reason,
                    "project": project,
                },
            )
            is not None
        )

        await content_guard(project, contentid)

        if changed:
            if reported:
                await get_project(project).call(
                    "post_report", database, userid, contentid, reason
                )
            await update_precomputation(database, contentid)

    return changed
