from fastapi import APIRouter
from fastapi_cache.decorator import cache

from immersive_library.models import (
    ContentListSuccess,
)
from immersive_library.routers.deprecated.filters import merge_tag_filters
from immersive_library.services import content as content_service

router = APIRouter(tags=["Content"])


@router.get(
    "/v1/content/{project}",
    deprecated=True,
    response_model_exclude_none=True,
    include_in_schema=False,
)
@cache(expire=60)
async def list_content(
    project: str, tag_filter: str | None = None, invert_filter: bool = False
) -> ContentListSuccess:
    return await content_service.list_content(
        project,
        whitelist=merge_tag_filters(
            None if invert_filter else tag_filter,
            tag_filter if invert_filter else None,
        ),
        limit=500,
    )
