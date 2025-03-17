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
    processed = 0
    for c in content:
        processed += 1
        await get_project(project).call("post_upload", database, userid, *c)

    return PlainTextResponse(
        f"Processed {processed} entries.",
    )
