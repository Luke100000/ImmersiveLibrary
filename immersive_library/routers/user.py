from fastapi import APIRouter, Depends, HTTPException
from fastapi_cache.decorator import cache

from immersive_library.caching import public_cache
from immersive_library.database import database
from immersive_library.models import (
    BanEntry,
    Error,
    LiteUserSuccess,
    PlainSuccess,
    UserListSuccess,
)
from immersive_library.services import users as user_service
from immersive_library.utils import (
    get_lite_user_class,
    moderator_guard,
    set_banned,
    set_moderator,
    update_precomputation,
    user_exists,
)

router = APIRouter(tags=["Users"])


@router.get("/v1/bans", tags=["Users"])
async def get_banned(userid: int = Depends(moderator_guard)) -> list[BanEntry]:
    assert userid
    content = await database.fetch_all(
        """
        SELECT oid, username
        FROM users
        WHERE banned == 1
    """
    )

    return [BanEntry(userid=u[0], username=u[1]) for u in content]


@router.get("/v1/user/{project}", tags=["Users"], response_model=UserListSuccess)
@public_cache()
@cache(expire=60)
async def get_users(
    project: str,
    limit: int = 100,
    offset: int = 0,
    order: user_service.UserOrder = user_service.UserOrder.OID,
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
    content = await user_service.list_users(
        project, 1, 0, user_service.UserOrder.OID, False, userid
    )
    if not content:
        raise HTTPException(404, "User doesn't exist")
    return LiteUserSuccess(user=get_lite_user_class(content[0]))


@router.put(
    "/v1/user/{userid}",
    tags=["Users"],
    responses={401: {"model": Error}, 403: {"model": Error}, 404: {"model": Error}},
)
async def set_user(
    userid: int,
    executor_userid: int = Depends(moderator_guard),
    banned: bool | None = None,
    moderator: bool | None = None,
    purge: bool = False,
) -> PlainSuccess:
    assert executor_userid

    if not await user_exists(database, userid):
        raise HTTPException(404, "User does not exist")

    # Change banned status
    if banned is not None:
        await set_banned(database, userid, banned)

    # Change moderator status
    if moderator is not None:
        await set_moderator(database, userid, moderator)

    # Delete the user's content
    if purge:
        async with database.transaction():
            await database.execute(
                "DELETE FROM content WHERE userid=:userid", {"userid": userid}
            )
            await database.execute(
                "DELETE FROM likes WHERE userid=:userid", {"userid": userid}
            )
            await update_precomputation(database)

    return PlainSuccess()
