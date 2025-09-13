from fastapi import APIRouter
from fastapi.requests import Request
from starlette.responses import HTMLResponse, FileResponse

from immersive_library.common import templates, projects
from immersive_library.routers.misc import get_statistics

router = APIRouter(tags=["Viewer"])


@router.get("/favicon.ico")
async def favicon():
    return FileResponse("static/favicon.ico")


@router.get("/{project}", response_class=HTMLResponse)
async def get_front(request: Request, project: str):
    if project not in projects:
        return HTMLResponse("Project not found", status_code=404)
    return templates.TemplateResponse(
        f"{project}/project.jinja",
        {
            "request": request,
            "project": project,
            "statistics": await get_statistics(project),
        },
    )


@router.get("/{project}/{contentid}", response_class=HTMLResponse)
async def get_skin_front(request: Request, project: str, contentid: int):
    if project not in projects:
        return HTMLResponse("Project not found", status_code=404)
    return templates.TemplateResponse(
        f"{project}/view.jinja",
        {"request": request, "project": project, "contentid": contentid},
    )
