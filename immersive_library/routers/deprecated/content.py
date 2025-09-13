from typing import Optional

from fastapi import APIRouter
from fastapi_cache.decorator import cache

from immersive_library.models import (
    ContentListSuccess,
)
from immersive_library.routers.content import inner_list_content_v2

router = APIRouter(tags=["Content"])


@router.get(
    "/v1/content/{project}",
    deprecated=True,
    response_model_exclude_none=True,
    include_in_schema=False,
)
@cache(expire=60)
async def list_content(
    project: str, tag_filter: Optional[str] = None, invert_filter: bool = False
) -> ContentListSuccess:
    return await inner_list_content_v2(
        project,
        whitelist=None if invert_filter else tag_filter,
        blacklist=tag_filter if invert_filter else None,
        limit=500,
    )
