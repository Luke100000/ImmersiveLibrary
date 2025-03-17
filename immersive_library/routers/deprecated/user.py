from typing import Optional

from fastapi import HTTPException, Header, APIRouter
from fastapi_cache.decorator import cache

from immersive_library.common import database
from immersive_library.models import (
    UserSuccess,
    Error,
)
from immersive_library.routers.content import TrackEnum, inner_list_content_v2
from immersive_library.utils import (
    token_to_userid,
    get_user_class,
)

router = APIRouter(tags=["Users"])


@router.get(
    "/v1/user/{project}/me",
    tags=["Users"],
    responses={401: {"model": Error}},
    response_model_exclude_none=True,
    response_model=UserSuccess,
    deprecated=True,
)
@cache(expire=60)
async def get_me(
    project: str,
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> UserSuccess:
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    return await get_user(project, userid)


@router.get(
    "/v1/user/{project}/{userid}",
    tags=["Users"],
    responses={404: {"model": Error}},
    response_model_exclude_none=True,
    response_model=UserSuccess,
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
