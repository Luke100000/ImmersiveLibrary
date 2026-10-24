from fastapi import APIRouter, Depends
from starlette.responses import PlainTextResponse

from immersive_library.common import database, get_project
from immersive_library.models import (
    Error,
)
from immersive_library.utils import (
    content_guard,
    moderator_guard,
    update_precomputation,
)

router = APIRouter(tags=["Admin"])


@router.get("/v1/tools/post-process/{project}", responses={401: {"model": Error}})
async def run_post_upload_callbacks(
    project: str, userid: int = Depends(moderator_guard)
) -> PlainTextResponse:
    content = await database.fetch_all(
        "SELECT oid FROM content WHERE project=:project",
        {"project": project},
    )

    log = []
    for record in content:
        for message in await get_project(project).call(
            "post_upload", database, userid, record["oid"]
        ):
            if message is not None:
                print(message)
                log.append(message)

    await update_precomputation(database)

    return PlainTextResponse(
        content="\n".join(log),
        media_type="text/plain",
        status_code=200,
    )


@router.get(
    "/v1/tools/post-process/{project}/{contentid}", responses={401: {"model": Error}}
)
async def run_post_upload_callbacks_content_id(
    project: str, contentid: int, userid: int = Depends(moderator_guard)
) -> PlainTextResponse:
    await content_guard(project, contentid)

    log = []
    for message in await get_project(project).call(
        "post_upload", database, userid, contentid
    ):
        if message is not None:
            print(message)
            log.append(message)

    await update_precomputation(database, contentid)

    return PlainTextResponse(
        content="\n".join(log),
        media_type="text/plain",
        status_code=200,
    )
