from immersive_library.database import database
from immersive_library.utils import has_liked, update_precomputation


async def set_like(contentid: int, userid: int, liked: bool) -> bool:
    if liked:
        inserted_userid = await database.fetch_val(
            """
            INSERT INTO likes (userid, contentid) VALUES(:userid, :contentid)
            ON CONFLICT (userid, contentid) DO NOTHING RETURNING userid
            """,
            {"userid": userid, "contentid": contentid},
        )
        if inserted_userid is None:
            return False
    else:
        if not await has_liked(database, userid, contentid):
            return False

        await database.execute(
            "DELETE FROM likes WHERE userid=:userid AND contentid=:contentid",
            {"userid": userid, "contentid": contentid},
        )

    await update_precomputation(database, contentid)
    return True
