from fastapi import APIRouter, Depends, HTTPException

from immersive_library.models import (
    Error,
    PlainSuccess,
)
from immersive_library.services import reports as report_service
from immersive_library.utils import (
    content_guard,
    logged_in_guard,
)

router = APIRouter(tags=["Users"], dependencies=[Depends(content_guard)])


@router.post(
    "/v1/report/{project}/{content_id}/{reason}",
    responses={401: {"model": Error}, 428: {"model": Error}},
)
async def add_report(
    project: str, content_id: int, reason: str, user_id: int = Depends(logged_in_guard)
) -> PlainSuccess:
    if not await report_service.set_report(project, content_id, user_id, reason, True):
        raise HTTPException(428, "Already reported")
    return PlainSuccess()


@router.delete(
    "/v1/report/{project}/{content_id}/{reason}",
    responses={401: {"model": Error}, 428: {"model": Error}},
)
async def delete_report(
    project: str,
    content_id: int,
    reason: str,
    user_id: int = Depends(logged_in_guard),
) -> PlainSuccess:
    if not await report_service.set_report(project, content_id, user_id, reason, False):
        raise HTTPException(428, "Not liked previously")
    return PlainSuccess()
