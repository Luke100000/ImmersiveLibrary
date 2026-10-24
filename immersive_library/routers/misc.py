from fastapi import APIRouter
from fastapi_cache.decorator import cache

from immersive_library.caching import public_cache
from immersive_library.services import statistics as statistics_service

router = APIRouter()


@router.get("/v1/stats/{project}")
@public_cache()
@cache(expire=60)
async def get_statistics(project: str) -> dict[str, str | int]:
    return await statistics_service.get_statistics(project)
