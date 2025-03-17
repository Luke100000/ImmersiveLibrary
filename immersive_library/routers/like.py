from typing import Optional

from fastapi import APIRouter
from fastapi import HTTPException, Header

from immersive_library.common import database
from immersive_library.models import (
    PlainSuccess,
    Error,
)
from immersive_library.utils import (
    token_to_userid,
    set_dirty,
    has_liked,
)

router = APIRouter(tags=["Likes"])


@router.post(
    "/v1/like/{project}/{contentid}",
    responses={401: {"model": Error}, 428: {"model": Error}},
)
async def add_like(
    project: str,
    contentid: int,
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> PlainSuccess:
    assert project
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if await has_liked(database, userid, contentid):
        raise HTTPException(428, "Already liked")

    await database.execute(
        "INSERT INTO likes (userid, contentid) VALUES(:userid, :contentid)",
        {"userid": userid, "contentid": contentid},
    )

    await set_dirty(database, contentid)

    return PlainSuccess()


@router.delete(
    "/v1/like/{project}/{contentid}",
    responses={401: {"model": Error}, 428: {"model": Error}},
)
async def delete_like(
    project: str,
    contentid: int,
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> PlainSuccess:
    assert project
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if not await has_liked(database, userid, contentid):
        raise HTTPException(428, "Not liked previously")

    await database.execute(
        "DELETE FROM likes WHERE userid=:userid AND contentid=:contentid",
        {"userid": userid, "contentid": contentid},
    )

    await set_dirty(database, contentid)

    return PlainSuccess()
