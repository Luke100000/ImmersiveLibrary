from functools import cache
from typing import cast

from fastapi import APIRouter, Query
from fastapi.requests import Request
from fastapi_cache.decorator import cache as cache_result
from jinja2 import TemplateNotFound
from starlette.responses import FileResponse, HTMLResponse

from immersive_library.caching import STATIC_CACHE_CONTROL
from immersive_library.common import projects, templates
from immersive_library.services import content as content_service
from immersive_library.services import statistics as statistics_service

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
    return templates.TemplateResponse(
        request,
        "index.jinja",
        {
            "projects": list(projects.keys()),
        },
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


@router.get("/{project}", response_class=HTMLResponse)
async def get_project_front(request: Request, project: str):
    if project not in projects:
        return HTMLResponse("Project not found", status_code=404)

    counts = cast(
        dict[str, str], await get_cached_statistics_counts(project, request=request)
    )
    return templates.TemplateResponse(
        request,
        get_template(project, "project"),
        {
            "project": project,
            "statistics": await statistics_service.get_statistics(
                project, counts=counts
            ),
        },
    )


@cache_result(expire=60)
async def get_cached_statistics_counts(
    project: str, request: Request
) -> dict[str, str]:
    """The cache decorator uses request to honor Cache-Control headers."""
    return await statistics_service.get_statistics_counts(project)


@router.get("/{project}/{content_id}", response_class=HTMLResponse)
async def get_content_front(request: Request, project: str, content_id: int):
    if project not in projects:
        return HTMLResponse("Project not found", status_code=404)

    content = await content_service.get_content(project, content_id)

    return templates.TemplateResponse(
        request,
        get_template(project, "view"),
        {"project": project, "content": content},
    )


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
