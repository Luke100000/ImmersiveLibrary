from functools import cache

from fastapi import APIRouter
from fastapi.requests import Request
from jinja2 import TemplateNotFound
from starlette.responses import FileResponse, HTMLResponse

from immersive_library.common import database, projects, templates
from immersive_library.routers.misc import get_statistics

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
    project_list = await database.fetch_all(
        "SELECT project FROM content GROUP BY project ORDER BY COUNT(*) DESC"
    )
    return templates.TemplateResponse(
        "index.jinja",
        {
            "request": request,
            "projects": [p["project"] for p in project_list],
        },
    )


@router.get("/favicon.ico")
async def favicon():
    return FileResponse("static/favicon.ico")


@router.get("/{project}", response_class=HTMLResponse)
async def get_project_front(request: Request, project: str):
    if project not in projects:
        return HTMLResponse("Project not found", status_code=404)

    return templates.TemplateResponse(
        get_template(project, "project"),
        {
            "request": request,
            "project": project,
            "statistics": await get_statistics(project),
        },
    )


@router.get("/{project}/{contentid}", response_class=HTMLResponse)
async def get_content_front(request: Request, project: str, contentid: int):
    if project not in projects:
        return HTMLResponse("Project not found", status_code=404)

    return templates.TemplateResponse(
        get_template(project, "view"),
        {"request": request, "project": project, "contentid": contentid},
    )
