from fastapi import APIRouter
from starlette.responses import Response

from immersive_library.routers.render import render_content

router = APIRouter()

router.add_api_route(
    "/v1/render/{project}/{content_id}",
    render_content,
    name="render_content_v1",
    response_class=Response,
    include_in_schema=False,
)
