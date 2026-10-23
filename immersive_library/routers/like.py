from fastapi import APIRouter, Depends, HTTPException

from immersive_library.common import database
from immersive_library.models import (
    Error,
    PlainSuccess,
)
from immersive_library.utils import (
    content_guard,
    has_liked,
    logged_in_guard,
    update_precomputation,
)

router = APIRouter(tags=["Likes"], dependencies=[Depends(content_guard)])


@router.post(
    "/v1/like/{project}/{contentid}",
    responses={401: {"model": Error}, 428: {"model": Error}},
)
async def add_like(
    project: str, contentid: int, userid: int = Depends(logged_in_guard)
) -> PlainSuccess:
    assert project

    inserted_userid = await database.fetch_val(
        """
        INSERT INTO likes (userid, contentid) VALUES(:userid, :contentid)
        ON CONFLICT (userid, contentid) DO NOTHING RETURNING userid
        """,
        {"userid": userid, "contentid": contentid},
    )
    if inserted_userid is None:
        raise HTTPException(428, "Already liked")

    await update_precomputation(database, contentid)

    return PlainSuccess()


@router.delete(
    "/v1/like/{project}/{contentid}",
    responses={401: {"model": Error}, 428: {"model": Error}},
)
async def delete_like(
    project: str, contentid: int, userid: int = Depends(logged_in_guard)
) -> PlainSuccess:
    assert project

    if not await has_liked(database, userid, contentid):
        raise HTTPException(428, "Not liked previously")

    await database.execute(
        "DELETE FROM likes WHERE userid=:userid AND contentid=:contentid",
        {"userid": userid, "contentid": contentid},
    )

    await update_precomputation(database, contentid)

    return PlainSuccess()
