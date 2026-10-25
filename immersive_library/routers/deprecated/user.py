from fastapi import APIRouter, Depends, HTTPException
from fastapi_cache.decorator import cache

from immersive_library.caching import public_cache
from immersive_library.database import database
from immersive_library.enums import ContentTrack, UserOrder
from immersive_library.models import (
    Error,
    LiteUserSuccess,
)
from immersive_library.routers.deprecated import serialization as legacy_content
from immersive_library.routers.deprecated.models import (
    User,
    UserListSuccess,
    UserSuccess,
)
from immersive_library.services import users as user_service
from immersive_library.utils import (
    get_lite_user_class,
    logged_in_guard,
)

router = APIRouter(tags=["Users"], deprecated=True)


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

    submissions = await legacy_content.list_content(
        project,
        track=ContentTrack.SUBMISSIONS,
        limit=200,
        userid=userid,
    )

    likes = await legacy_content.list_content(
        project,
        track=ContentTrack.LIKES,
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


@router.get("/v1/user/{project}", tags=["Users"], response_model=UserListSuccess)
@public_cache()
@cache(expire=60)
async def get_users(
    project: str,
    limit: int = 100,
    offset: int = 0,
    order: UserOrder = UserOrder.OID,
    descending: bool = False,
) -> UserListSuccess:
    content = await user_service.list_users(project, limit, offset, order, descending)
    return UserListSuccess(users=[get_lite_user_class(c) for c in content])


@router.get(
    "/v2/user/{project}/{userid}",
    tags=["Users"],
    responses={404: {"model": Error}},
    response_model=LiteUserSuccess,
)
@public_cache()
@cache(expire=60)
async def get_user_v2(project: str, userid: int) -> LiteUserSuccess:
    content = await user_service.list_users(project, 1, 0, UserOrder.OID, False, userid)
    if not content:
        raise HTTPException(404, "User doesn't exist")
    return LiteUserSuccess(user=get_lite_user_class(content[0]))
