from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_cache.decorator import cache

from immersive_library.caching import public_cache
from immersive_library.database import database
from immersive_library.dependencies import (
    UserFilter,
    optional_userid,
    resolve_user_filter,
)
from immersive_library.enums import UserOrder
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


@router.get("/v1/bans", tags=["Users"], dependencies=[Depends(moderator_guard)])
async def get_banned() -> list[BanEntry]:
    content = await database.fetch_all(
        """
        SELECT oid, username
        FROM users
        WHERE banned == 1
    """
    )

    return [BanEntry(userid=u[0], username=u[1]) for u in content]


@router.get("/v3/user/{project}")
@public_cache()
@cache(expire=60)
async def get_users_v3(
    project: str,
    limit: int = Query(
        100, ge=1, le=500, description="The maximum number of users to fetch."
    ),
    offset: int = Query(
        0, ge=0, description="The offset to start fetching users from."
    ),
    order: UserOrder = Query(
        UserOrder.OID, description="Sort order; ties are resolved by user ID."
    ),
    descending: bool = Query(False, description="Sort in descending order."),
) -> UserListSuccess:
    rows = await user_service.list_users(project, limit + 1, offset, order, descending)
    return UserListSuccess(
        users=[get_lite_user_class(row) for row in rows[:limit]],
        has_more=len(rows) > limit,
    )


@router.get("/v3/user/{project}/{userid}")
@public_cache()
@cache(expire=60)
async def get_user_v3(
    project: str,
    userid: UserFilter,
    viewer_id: Annotated[int | None, Depends(optional_userid)] = None,
) -> LiteUserSuccess:
    target_userid = resolve_user_filter(userid, viewer_id)
    rows = await user_service.list_users(
        project, 1, 0, UserOrder.OID, False, target_userid
    )
    if not rows:
        raise HTTPException(404, "User doesn't exist")
    return LiteUserSuccess(user=get_lite_user_class(rows[0]))


@router.put(
    "/v1/user/{userid}",
    tags=["Users"],
    dependencies=[Depends(moderator_guard)],
    responses={401: {"model": Error}, 403: {"model": Error}, 404: {"model": Error}},
)
async def set_user(
    userid: int,
    banned: bool | None = None,
    moderator: bool | None = None,
    purge: bool = False,
) -> PlainSuccess:
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
