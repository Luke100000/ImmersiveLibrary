from immersive_library.database import database
from immersive_library.utils import content_guard, update_precomputation


async def set_like(project: str, contentid: int, userid: int, liked: bool) -> bool:
    async with database.transaction():
        if liked:
            statement = """
                INSERT INTO likes (userid, contentid)
                SELECT :userid, :contentid FROM content WHERE oid=:contentid AND project=:project
                ON CONFLICT (userid, contentid) DO NOTHING RETURNING userid
            """
        else:
            statement = """
                DELETE FROM likes WHERE userid=:userid AND contentid=:contentid
                AND EXISTS (SELECT 1 FROM content WHERE oid=:contentid AND project=:project)
                RETURNING userid
            """
        changed = (
            await database.fetch_val(
                statement,
                {"userid": userid, "contentid": contentid, "project": project},
            )
            is not None
        )
        await content_guard(project, contentid)
        if changed:
            await update_precomputation(database, contentid)
    return changed
