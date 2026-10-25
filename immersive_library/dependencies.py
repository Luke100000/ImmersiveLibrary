from typing import Annotated, Literal

from fastapi import Header, HTTPException

from immersive_library.database import database
from immersive_library.utils import sha256

UserFilter = int | Literal["me"]


async def optional_user_id(
    authorization: Annotated[str | None, Header()] = None,
) -> int | None:
    if authorization is None:
        return None

    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token:
        raise HTTPException(
            401, "Token invalid", headers={"WWW-Authenticate": "Bearer"}
        )

    user_id = await database.fetch_val(
        """
        SELECT users.oid FROM users
        JOIN user_tokens ON user_tokens.user_id=users.oid WHERE token=:token
        """,
        {"token": sha256(token)},
    )

    if user_id is None:
        raise HTTPException(
            401, "Token invalid", headers={"WWW-Authenticate": "Bearer"}
        )

    return user_id


def resolve_user_filter(value: UserFilter | None, viewer_id: int | None) -> int | None:
    if value != "me":
        return value

    if viewer_id is None:
        raise HTTPException(
            401, "Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )

    return viewer_id
