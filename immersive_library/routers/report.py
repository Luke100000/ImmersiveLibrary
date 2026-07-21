from fastapi import APIRouter, Depends, HTTPException

from immersive_library.common import database, get_project
from immersive_library.models import (
    Error,
    PlainSuccess,
)
from immersive_library.utils import (
    content_exists,
    has_reported,
    logged_in_guard,
    update_precomputation,
)

router = APIRouter(tags=["Users"])


@router.post(
    "/v1/report/{project}/{contentid}/{reason}",
    responses={401: {"model": Error}, 428: {"model": Error}},
)
async def add_report(
    project: str, contentid: int, reason: str, userid: int = Depends(logged_in_guard)
) -> PlainSuccess:
    if not await content_exists(database, project, contentid):
        raise HTTPException(404, "Content not found")
    await get_project(project).validate(
        "pre_report", database, userid, contentid, reason
    )

    if await has_reported(database, userid, contentid, reason):
        raise HTTPException(428, "Already reported")

    await database.execute(
        "INSERT OR IGNORE INTO reports (userid, contentid, reason) VALUES(:userid, :contentid, :reason)",
        {"userid": userid, "contentid": contentid, "reason": reason},
    )

    # Call validators for eventual post-processing
    await get_project(project).call("post_report", database, userid, contentid, reason)

    await update_precomputation(database, contentid)

    return PlainSuccess()


@router.delete(
    "/v1/report/{project}/{contentid}/{reason}",
    responses={401: {"model": Error}, 428: {"model": Error}},
)
async def delete_report(
    project: str,
    contentid: int,
    reason: str,
    userid: int = Depends(logged_in_guard),
) -> PlainSuccess:
    if not await content_exists(database, project, contentid):
        raise HTTPException(404, "Content not found")

    if not await has_reported(database, userid, contentid, reason):
        raise HTTPException(428, "Not liked previously")

    await database.execute(
        "DELETE FROM reports WHERE userid=:userid AND contentid=:contentid AND reason=:reason",
        {"userid": userid, "contentid": contentid, "reason": reason},
    )

    await update_precomputation(database, contentid)

    return PlainSuccess()
