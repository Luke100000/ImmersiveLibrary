from fastapi import APIRouter, Depends, HTTPException
from fastapi_cache.decorator import cache

from immersive_library.database import database
from immersive_library.enums import TrackEnum
from immersive_library.models import (
    Error,
)
from immersive_library.routers.deprecated.models import User, UserSuccess
from immersive_library.services import content as content_service
from immersive_library.utils import (
    logged_in_guard,
)

router = APIRouter(tags=["Users"])


@router.get(
    "/v1/user/{project}/me",
    tags=["Users"],
    responses={401: {"model": Error}},
    response_model_exclude_none=True,
    response_model=UserSuccess,
    deprecated=True,
    include_in_schema=False,
)
@cache(expire=60)
async def get_me(project: str, userid: int = Depends(logged_in_guard)) -> UserSuccess:
    return await get_user(project, userid)


@router.get(
    "/v1/user/{project}/{userid}",
    tags=["Users"],
    responses={404: {"model": Error}},
    response_model_exclude_none=True,
    response_model=UserSuccess,
    include_in_schema=False,
    deprecated=True,
)
@cache(expire=60)
async def get_user(
    project: str,
    userid: int,
) -> UserSuccess:
    content = await database.fetch_one(
        "SELECT oid, username, moderator FROM users WHERE oid=:userid",
        {"userid": userid},
    )

    if content is None:
        raise HTTPException(404, "User doesn't exist")

    submissions = await content_service.list_content(
        project,
        track=TrackEnum.SUBMISSIONS,
        limit=200,
        userid=userid,
    )

    likes = await content_service.list_content(
        project,
        track=TrackEnum.LIKES,
        limit=200,
        userid=userid,
    )

    return UserSuccess(
        user=User(
            userid=content["oid"],
            username=content["username"],
            moderator=content["moderator"] > 0,
            likes_received=sum(item.likes for item in submissions.contents),
            submissions=submissions.contents,
            likes=likes.contents,
        )
    )
