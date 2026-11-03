from fastapi import APIRouter, HTTPException, Query, Request
from starlette.responses import Response

from immersive_library.common import projects
from immersive_library.enums import RenderPreset
from immersive_library.previews import GRID_LIMIT, PRESET_SIZES
from immersive_library.ratelimit import client_ip
from immersive_library.services import collections as collection_service
from immersive_library.services import render as render_service
from immersive_library.services import users as user_service

router = APIRouter(tags=["Content"])

JPEG_RESPONSE = {200: {"content": {"image/jpeg": {}}}}


def project_guard(project: str) -> None:
    if project not in projects:
        raise HTTPException(404, "Project not found")


def jpeg_response(jpeg_bytes: bytes) -> Response:
    max_age = render_service.PREVIEW_CACHE_SECONDS
    return Response(
        content=jpeg_bytes,
        media_type="image/jpeg",
        headers={"Cache-Control": f"public, max-age={max_age}, must-revalidate"},
    )


@router.get(
    "/v3/render/{project}/{content_id}",
    response_class=Response,
    responses=JPEG_RESPONSE,
)
async def render_content(
    request: Request,
    project: str,
    content_id: int,
    preset: RenderPreset = Query(RenderPreset.EMBED),
) -> Response:
    project_guard(project)
    return jpeg_response(
        await render_service.content_preview(
            request.app.state.renderer,
            client_ip(request),
            project,
            content_id,
            PRESET_SIZES[preset],
        )
    )


@router.get(
    "/v3/render/{project}/users/{user_id}",
    response_class=Response,
    responses=JPEG_RESPONSE,
)
async def render_user(request: Request, project: str, user_id: int) -> Response:
    project_guard(project)
    previews = await user_service.preview_ids(project, [user_id], GRID_LIMIT)
    return jpeg_response(
        await render_service.grid_preview(
            request.app.state.renderer,
            client_ip(request),
            project,
            f"user:{user_id}",
            previews[user_id],
        )
    )


@router.get(
    "/v3/render/{project}/collections/{collection_id}",
    response_class=Response,
    responses=JPEG_RESPONSE,
)
async def render_collection(
    request: Request, project: str, collection_id: int
) -> Response:
    project_guard(project)

    # Only public collections, since embeds are fetched without the viewer's token.
    await collection_service.get_collection(project, collection_id, None)

    previews = await collection_service.preview_ids(
        project, [collection_id], None, GRID_LIMIT
    )
    return jpeg_response(
        await render_service.grid_preview(
            request.app.state.renderer,
            client_ip(request),
            project,
            f"collection:{collection_id}",
            previews[collection_id],
        )
    )
