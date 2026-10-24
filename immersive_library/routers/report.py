from fastapi import APIRouter, Depends, HTTPException

from immersive_library.common import get_project
from immersive_library.database import database
from immersive_library.models import (
    Error,
    PlainSuccess,
)
from immersive_library.utils import (
    content_guard,
    has_reported,
    logged_in_guard,
    update_precomputation,
)

router = APIRouter(tags=["Users"], dependencies=[Depends(content_guard)])


@router.post(
    "/v1/report/{project}/{contentid}/{reason}",
    responses={401: {"model": Error}, 428: {"model": Error}},
)
async def add_report(
    project: str, contentid: int, reason: str, userid: int = Depends(logged_in_guard)
) -> PlainSuccess:
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
        raise HTTPException(428, "Already reported")

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
    assert project

    if not await has_reported(database, userid, contentid, reason):
        raise HTTPException(428, "Not liked previously")

    await database.execute(
        "DELETE FROM reports WHERE userid=:userid AND contentid=:contentid AND reason=:reason",
        {"userid": userid, "contentid": contentid, "reason": reason},
    )

    await update_precomputation(database, contentid)

    return PlainSuccess()
