from functools import cache
from typing import cast

from fastapi import APIRouter, Query
from fastapi.requests import Request
from fastapi_cache.decorator import cache as cache_result
from jinja2 import TemplateNotFound
from starlette.responses import FileResponse, HTMLResponse

from immersive_library.caching import STATIC_CACHE_CONTROL
from immersive_library.common import projects, templates
from immersive_library.enums import UserOrder
from immersive_library.services import content as content_service
from immersive_library.services import statistics as statistics_service
from immersive_library.services import users as user_service
from immersive_library.utils import get_lite_user_class

router = APIRouter(tags=["Viewer"])


@cache
def get_template(project: str, file: str):
    template_name = f"{project}/{file}.jinja"
    try:
        templates.env.get_template(template_name)
    except TemplateNotFound:
        template_name = f"default/{file}.jinja"
    return template_name


@router.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    statistics = {
        project: await statistics_service.get_statistics(
            project,
            counts=cast(
                dict[str, str],
                await get_cached_statistics_counts(project, request=request),
            ),
        )
        for project in projects
    }
    return templates.TemplateResponse(
        request,
        "home.jinja",
        {"projects": projects, "statistics": statistics},
    )


@router.get("/favicon.ico")
async def favicon():
    return FileResponse(
        "static/favicon.ico", headers={"Cache-Control": STATIC_CACHE_CONTROL}
    )


@router.get("/privacy", response_class=HTMLResponse)
async def get_privacy(request: Request):
    return templates.TemplateResponse(request, "privacy.jinja")


@router.get("/tos", response_class=HTMLResponse)
async def get_tos(request: Request):
    return templates.TemplateResponse(request, "tos.jinja")


@router.get("/contact", response_class=HTMLResponse)
async def get_contact(request: Request):
    return templates.TemplateResponse(request, "contact.jinja")


@router.get("/render", response_class=HTMLResponse)
async def get_render_shell(request: Request):
    return templates.TemplateResponse(
        request,
        "default/render.jinja",
        {"project": None, "content": None, "width": 512, "height": 512},
    )


@cache_result(expire=60)
async def get_cached_statistics_counts(
    project: str, request: Request
) -> dict[str, str]:
    """The cache decorator uses request to honor Cache-Control headers."""
    return await statistics_service.get_statistics_counts(project)


@router.get("/render/{project}/{content_id}", response_class=HTMLResponse)
async def get_render_view(
    request: Request,
    project: str,
    content_id: int,
    width: int = Query(512, ge=64, le=2048),
    height: int = Query(512, ge=64, le=2048),
):
    if project not in projects:
        return HTMLResponse("Project not found", status_code=404)

    content = await content_service.get_content(project, content_id)

    return templates.TemplateResponse(
        request,
        get_template(project, "render"),
        {
            "project": project,
            "content": content,
            "width": width,
            "height": height,
        },
    )


def project_response(request: Request, project: str, template: str, **context):
    if project not in projects:
        return HTMLResponse("Project not found", status_code=404)
    return templates.TemplateResponse(
        request,
        template,
        {"project": project, "project_info": projects[project], **context},
    )


@router.get("/{project}", response_class=HTMLResponse)
async def get_content_library(request: Request, project: str):
    return project_response(
        request, project, "library/content.jinja", section="content"
    )


@router.get("/{project}/users", response_class=HTMLResponse)
async def get_user_library(request: Request, project: str):
    return project_response(request, project, "library/users.jinja", section="users")


@router.get("/{project}/users/{user_id}", response_class=HTMLResponse)
async def get_user_front(request: Request, project: str, user_id: int):
    if project not in projects:
        return HTMLResponse("Project not found", status_code=404)

    rows = await user_service.list_users(project, 1, 0, UserOrder.OID, False, user_id)
    if not rows:
        return HTMLResponse("User not found", status_code=404)

    return project_response(
        request,
        project,
        "library/user.jinja",
        section="users",
        user=get_lite_user_class(rows[0]),
    )


@router.get("/{project}/collections", response_class=HTMLResponse)
async def get_collection_library(request: Request, project: str):
    return project_response(
        request, project, "library/collections.jinja", section="collections"
    )


# Collections can be private, so the page loads them with the viewer's token.
@router.get("/{project}/collections/{collection_id}", response_class=HTMLResponse)
async def get_collection_front(request: Request, project: str, collection_id: int):
    return project_response(
        request,
        project,
        "library/collection.jinja",
        section="collections",
        collection_id=collection_id,
    )


# Declared last so the named sections above take precedence over content IDs.
@router.get("/{project}/{content_id}", response_class=HTMLResponse)
async def get_content_front(request: Request, project: str, content_id: int):
    if project not in projects:
        return HTMLResponse("Project not found", status_code=404)

    content = await content_service.get_content(project, content_id)

    return project_response(
        request,
        project,
        get_template(project, "view"),
        section="content",
        content=content,
    )
