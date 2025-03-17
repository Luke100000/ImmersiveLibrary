from typing import Optional

from fastapi import APIRouter
from fastapi import HTTPException, Header

from immersive_library.common import database, get_project
from immersive_library.models import (
    PlainSuccess,
    Error,
)
from immersive_library.utils import (
    token_to_userid,
    set_dirty,
    has_reported,
)

router = APIRouter(tags=["Users"])


@router.post(
    "/v1/report/{project}/{contentid}/{reason}",
    responses={401: {"model": Error}, 428: {"model": Error}},
)
async def add_report(
    project: str,
    contentid: int,
    reason: str,
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> PlainSuccess:
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if await has_reported(database, userid, contentid, reason):
        raise HTTPException(428, "Already reported")

    await database.execute(
        "INSERT INTO reports (userid, contentid, reason) VALUES(:userid, :contentid, :reason)",
        {"userid": userid, "contentid": contentid, "reason": reason},
    )

    # Call validators for eventual post-processing
    await get_project(project).call("post_report", database, userid, contentid)

    await set_dirty(database, contentid)

    return PlainSuccess()


@router.delete(
    "/v1/report/{project}/{contentid}/{reason}",
    responses={401: {"model": Error}, 428: {"model": Error}},
)
async def delete_report(
    project: str,
    contentid: int,
    reason: str,
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> PlainSuccess:
    assert project
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if not await has_reported(database, userid, contentid, reason):
        raise HTTPException(428, "Not liked previously")

    await database.execute(
        "DELETE FROM reports WHERE userid=:userid AND contentid=:contentid AND reason=:reason",
        {"userid": userid, "contentid": contentid, "reason": reason},
    )

    await set_dirty(database, contentid)

    return PlainSuccess()
