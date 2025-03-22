from enum import Enum
from typing import List, Optional

from fastapi import HTTPException, Header, Query, APIRouter
from fastapi_cache.decorator import cache

from immersive_library.common import database
from immersive_library.models import (
    PlainSuccess,
    UserListSuccess,
    BanEntry,
    Error,
    LiteUserSuccess,
)
from immersive_library.utils import (
    token_to_userid,
    is_moderator,
    set_moderator,
    set_banned,
    user_exists,
    get_lite_user_class,
)

router = APIRouter(tags=["Users"])


@router.get(
    "/v1/bans",
    tags=["Users"],
)
async def get_banned() -> List[BanEntry]:
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


@router.get(
    "/v1/user/{project}",
    tags=["Users"],
    response_model=UserListSuccess,
)
@cache(expire=60)
async def get_users(
    project: str,
    limit: int = 100,
    offset: int = 0,
    order: UserOrder = UserOrder.OID,
    descending: bool = False,
    _userid: Optional[int] = Query(None, include_in_schema=False),
) -> UserListSuccess:
    content = await database.fetch_all(
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
            ) likes_received ON likes_received.userid = users.oid

            WHERE users.banned = 0
            {"" if _userid is None else f"AND users.oid = {int(_userid)}"}

            ORDER BY {order.name} {"DESC" if descending else "ASC"}
            LIMIT :limit
            OFFSET :offset
        """,
        {"limit": limit, "offset": offset, "project": project},
    )
    return UserListSuccess(users=[get_lite_user_class(c) for c in content])


@router.get(
    "/v2/user/{project}/{userid}",
    tags=["Users"],
    responses={404: {"model": Error}},
    response_model=LiteUserSuccess,
)
@cache(expire=60)
async def get_user_v2(project: str, userid: int) -> LiteUserSuccess:
    users = await get_users(project, 1, 0, UserOrder.OID, False, userid)
    if not users.users:
        raise HTTPException(404, "User doesn't exist")
    return LiteUserSuccess(user=users.users[0])


@router.put(
    "/v1/user/{userid}",
    tags=["Users"],
    responses={401: {"model": Error}, 403: {"model": Error}, 404: {"model": Error}},
)
async def set_user(
    userid: int,
    token: Optional[str] = None,
    authorization: str = Header(None),
    banned: Optional[bool] = None,
    moderator: Optional[bool] = None,
    purge=False,
) -> PlainSuccess:
    executor_userid = await token_to_userid(database, token, authorization)

    if executor_userid is None:
        raise HTTPException(401, "Token invalid")

    if not await is_moderator(database, executor_userid):
        raise HTTPException(403, "Not a moderator")

    if not await user_exists(database, userid):
        raise HTTPException(404, "User does not exist")

    # Change banned status
    if banned is not None:
        await set_banned(database, userid, banned)

    # Change moderator status
    if moderator is not None:
        await set_moderator(database, userid, moderator)

    # Delete the users content
    if purge is True:
        await database.execute(
            "DELETE FROM content WHERE userid=:userid", {"userid": userid}
        )
        await database.execute(
            "DELETE FROM likes WHERE userid=:userid", {"userid": userid}
        )

    return PlainSuccess()
