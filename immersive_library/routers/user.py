from enum import Enum
from typing import List, Optional

from databases.interfaces import Record
from fastapi import APIRouter, Depends, HTTPException
from fastapi_cache.decorator import cache

from immersive_library.common import database
from immersive_library.models import (
    BanEntry,
    Error,
    LiteUserSuccess,
    PlainSuccess,
    UserListSuccess,
)
from immersive_library.utils import (
    get_lite_user_class,
    moderator_guard,
    set_banned,
    set_moderator,
    user_exists,
)

router = APIRouter(tags=["Users"])


@router.get("/v1/bans", tags=["Users"])
async def get_banned(userid: int = Depends(moderator_guard)) -> List[BanEntry]:
    assert userid
    content = await database.fetch_all(
        """
        SELECT oid, username
        FROM users
        WHERE banned == 1
    """
    )

    return [BanEntry(userid=u[0], username=u[1]) for u in content]


class UserOrder(str, Enum):
    OID = "date"
    SUBMISSION_COUNT = "submissions"
    LIKES_GIVEN = "likes_given"
    LIKES_RECEIVED = "likes_received"


@router.get("/v1/user/{project}", tags=["Users"], response_model=UserListSuccess)
@cache(expire=60)
async def get_users(
    project: str,
    limit: int = 100,
    offset: int = 0,
    order: UserOrder = UserOrder.OID,
    descending: bool = False,
) -> UserListSuccess:
    content = await get_users_inner(project, limit, offset, order, descending)
    return UserListSuccess(users=[get_lite_user_class(c) for c in content])


@router.get(
    "/v2/user/{project}/{userid}",
    tags=["Users"],
    responses={404: {"model": Error}},
    response_model=LiteUserSuccess,
)
@cache(expire=60)
async def get_user_v2(project: str, userid: int) -> LiteUserSuccess:
    content = await get_users_inner(project, 1, 0, UserOrder.OID, False, userid)
    if not content:
        raise HTTPException(404, "User doesn't exist")
    return LiteUserSuccess(user=get_lite_user_class(content[0]))


async def get_users_inner(
    project: str,
    limit: int,
    offset: int,
    order: UserOrder,
    descending: bool,
    userid: Optional[int] = None,
) -> list[Record]:
    return await database.fetch_all(
        f"""
            SELECT users.oid,
                   users.username,
                   users.moderator,
                   COALESCE(submitted_content.submission_count, 0) as submission_count,
                   COALESCE(likes_given.count, 0) as likes_given,
                   COALESCE(likes_received.count, 0) as likes_received
            FROM users

            LEFT JOIN (
                SELECT content.userid, COUNT(content.oid) as submission_count
                FROM content
                WHERE content.project = :project
                GROUP BY content.userid
            ) submitted_content ON submitted_content.userid = users.oid

            LEFT JOIN (
                SELECT likes.userid, COUNT(likes.oid) as count
                FROM likes
                GROUP BY likes.userid
            ) likes_given ON likes_given.userid = users.oid

            LEFT JOIN (
                SELECT c2.userid, SUM(COALESCE(precomputation.likes, 0)) as count
                FROM content c2
                LEFT JOIN precomputation ON precomputation.contentid = c2.oid
                WHERE c2.project = :project
                GROUP BY c2.userid
            ) likes_receivedgi ON likes_received.userid = users.oid

            WHERE users.banned = 0
            {"" if userid is None else f"AND users.oid = {int(userid)}"}

            ORDER BY {order.name} {"DESC" if descending else "ASC"}
            LIMIT :limit
            OFFSET :offset
        """,
        {"limit": limit, "offset": offset, "project": project},
    )


@router.put(
    "/v1/user/{userid}",
    tags=["Users"],
    responses={401: {"model": Error}, 403: {"model": Error}, 404: {"model": Error}},
)
async def set_user(
    userid: int,
    executor_userid: int = Depends(moderator_guard),
    banned: Optional[bool] = None,
    moderator: Optional[bool] = None,
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
        await database.execute(
            "DELETE FROM content WHERE userid=:userid", {"userid": userid}
        )
        await database.execute(
            "DELETE FROM likes WHERE userid=:userid", {"userid": userid}
        )

    return PlainSuccess()
