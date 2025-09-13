from fastapi import APIRouter, Depends, HTTPException
from fastapi_cache.decorator import cache

from immersive_library.common import database
from immersive_library.models import (
    Error,
    UserSuccess,
)
from immersive_library.routers.content import TrackEnum, inner_list_content_v2
from immersive_library.utils import (
    get_user_class,
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

    submissions = await inner_list_content_v2(
        project,
        track=TrackEnum.SUBMISSIONS,
        limit=200,
        userid=userid,
    )

    likes = await inner_list_content_v2(
        project,
        track=TrackEnum.LIKES,
        limit=200,
        userid=userid,
    )

    return UserSuccess(
        user=await get_user_class(
            content["oid"],
            content["username"],
            content["moderator"],
            submissions.contents,
            likes.contents,
        )
    )
