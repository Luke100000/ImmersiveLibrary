from fastapi import APIRouter, Depends
from starlette.responses import PlainTextResponse

from immersive_library.common import get_project
from immersive_library.database import database
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
    project: str, user_id: int = Depends(moderator_guard)
) -> PlainTextResponse:
    content = await database.fetch_all(
        "SELECT oid FROM content WHERE project=:project",
        {"project": project},
    )

    log = []
    for record in content:
        log += await get_project(project).call(
            "post_upload", database, user_id, record["oid"]
        )

    await update_precomputation(database)

    return PlainTextResponse(
        "\n".join(message for message in log if message is not None)
    )


@router.get(
    "/v1/tools/post-process/{project}/{content_id}", responses={401: {"model": Error}}
)
async def run_post_upload_callbacks_content_id(
    project: str, content_id: int, user_id: int = Depends(moderator_guard)
) -> PlainTextResponse:
    await content_guard(project, content_id)

    log = await get_project(project).call("post_upload", database, user_id, content_id)

    await update_precomputation(database, content_id)

    return PlainTextResponse(
        "\n".join(message for message in log if message is not None)
    )
