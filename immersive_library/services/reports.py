from immersive_library.common import get_project
from immersive_library.database import database
from immersive_library.utils import has_reported, update_precomputation


async def set_report(
    project: str, contentid: int, userid: int, reason: str, reported: bool
) -> bool:
    if reported:
        await get_project(project).validate(
            "pre_report", database, userid, contentid, reason
        )

        inserted_userid = await database.fetch_val(
            """
            INSERT INTO reports (userid, contentid, reason) VALUES(:userid, :contentid, :reason)
            ON CONFLICT (userid, contentid, reason) DO NOTHING RETURNING userid
            """,
            {"userid": userid, "contentid": contentid, "reason": reason},
        )
        if inserted_userid is None:
            return False

        # Call validators for eventual post-processing
        await get_project(project).call(
            "post_report", database, userid, contentid, reason
        )
    else:
        if not await has_reported(database, userid, contentid, reason):
            return False

        await database.execute(
            "DELETE FROM reports WHERE userid=:userid AND contentid=:contentid AND reason=:reason",
            {"userid": userid, "contentid": contentid, "reason": reason},
        )

    await update_precomputation(database, contentid)
    return True
