from fastapi import APIRouter, Depends, HTTPException

from immersive_library.models import (
    Error,
    PlainSuccess,
)
from immersive_library.services import likes as like_service
from immersive_library.utils import (
    content_guard,
    logged_in_guard,
)

router = APIRouter(tags=["Likes"], dependencies=[Depends(content_guard)])


@router.post(
    "/v1/like/{project}/{contentid}",
    responses={401: {"model": Error}, 428: {"model": Error}},
)
async def add_like(
    project: str, contentid: int, userid: int = Depends(logged_in_guard)
) -> PlainSuccess:
    if not await like_service.set_like(project, contentid, userid, True):
        raise HTTPException(428, "Already liked")
    return PlainSuccess()


@router.delete(
    "/v1/like/{project}/{contentid}",
    responses={401: {"model": Error}, 428: {"model": Error}},
)
async def delete_like(
    project: str, contentid: int, userid: int = Depends(logged_in_guard)
) -> PlainSuccess:
    if not await like_service.set_like(project, contentid, userid, False):
        raise HTTPException(428, "Not liked previously")
    return PlainSuccess()
