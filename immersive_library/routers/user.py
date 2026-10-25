from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_cache.decorator import cache

from immersive_library.caching import public_cache
from immersive_library.database import database
from immersive_library.dependencies import (
    UserFilter,
    optional_user_id,
    resolve_user_filter,
)
from immersive_library.enums import UserOrder
from immersive_library.models import (
    Error,
    LiteUserSuccess,
    PlainSuccess,
    UserListSuccess,
)
from immersive_library.routers.deprecated.models import BanEntry
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


@router.get("/v3/user/{project}", response_model=UserListSuccess)
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


@router.get("/v3/user/{project}/{user_id}", response_model=LiteUserSuccess)
@public_cache()
@cache(expire=60)
async def get_user_v3(
    project: str,
    user_id: UserFilter,
    viewer_id: Annotated[int | None, Depends(optional_user_id)] = None,
) -> LiteUserSuccess:
    target_user_id = resolve_user_filter(user_id, viewer_id)
    rows = await user_service.list_users(
        project, 1, 0, UserOrder.OID, False, target_user_id
    )
    if not rows:
        raise HTTPException(404, "User doesn't exist")
    return LiteUserSuccess(user=get_lite_user_class(rows[0]))


@router.put(
    "/v1/user/{user_id}",
    tags=["Users"],
    dependencies=[Depends(moderator_guard)],
    responses={401: {"model": Error}, 403: {"model": Error}, 404: {"model": Error}},
)
async def set_user(
    user_id: int,
    banned: bool | None = None,
    moderator: bool | None = None,
    purge: bool = False,
) -> PlainSuccess:
    if not await user_exists(database, user_id):
        raise HTTPException(404, "User does not exist")

    # Change banned status
    if banned is not None:
        await set_banned(database, user_id, banned)

    # Change moderator status
    if moderator is not None:
        await set_moderator(database, user_id, moderator)

    # Delete the user's content
    if purge:
        async with database.transaction():
            await database.execute(
                "DELETE FROM content WHERE user_id=:user_id", {"user_id": user_id}
            )
            await database.execute(
                "DELETE FROM likes WHERE user_id=:user_id", {"user_id": user_id}
            )
            await update_precomputation(database)

    return PlainSuccess()
