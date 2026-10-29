from fastapi import APIRouter
from fastapi_cache.decorator import cache

from immersive_library.caching import public_cache
from immersive_library.routers.deprecated.models import (
    LegacyTagDictSuccess,
)
from immersive_library.services import tags as tag_service

router = APIRouter(tags=["Tags"], deprecated=True)


@router.get("/v1/tag/{project}", response_model=LegacyTagDictSuccess)
@public_cache()
@cache(expire=60)
async def list_project_tags(
    project: str, limit: int = 100, offset: int = 0
) -> LegacyTagDictSuccess:
    rows = await tag_service.list_project_tags(project, limit, offset)
    return LegacyTagDictSuccess(tags={row["tag"]: row["count"] for row in rows})
