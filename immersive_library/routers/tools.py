from typing import Optional

from fastapi import HTTPException, Header, APIRouter
from starlette.responses import PlainTextResponse

from immersive_library.common import database, get_project
from immersive_library.models import (
    Error,
)
from immersive_library.utils import (
    token_to_userid,
    is_moderator,
)

router = APIRouter(tags=["Admin"])


@router.get(
    "/v1/tools/post-process/{project}",
    responses={401: {"model": Error}},
)
async def run_post_upload_callbacks(
    project: str, token: Optional[str] = None, authorization: str = Header(None)
) -> PlainTextResponse:
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if not await is_moderator(database, userid):
        raise HTTPException(401, "Not an moderator")

    content = await database.fetch_all(
        "SELECT oid FROM content WHERE project=:project",
        {"project": project},
    )

    # Call validators for eventual post-processing
    log = []
    for c in content:
        for message in await get_project(project).call(
            "post_upload", database, userid, c["oid"]
        ):
            if message is not None:
                print(message)
                log.append(message)

    return PlainTextResponse(
        content="\n".join(log),
        media_type="text/plain",
        status_code=200,
    )


@router.get(
    "/v1/tools/post-process/{project}/{content_id}",
    responses={401: {"model": Error}},
)
async def run_post_upload_callbacks_content_id(
    project: str,
    content_id: str,
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> PlainTextResponse:
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if not await is_moderator(database, userid):
        raise HTTPException(401, "Not an moderator")

    # Call validators for eventual post-processing
    log = []
    for message in await get_project(project).call(
        "post_upload", database, userid, content_id
    ):
        if message is not None:
            print(message)
            log.append(message)

    return PlainTextResponse(
        content="\n".join(log),
        media_type="text/plain",
        status_code=200,
    )
