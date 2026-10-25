from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_cache.decorator import cache

from immersive_library.caching import public_cache
from immersive_library.database import database
from immersive_library.models import (
    Error,
    PlainSuccess,
    TagCount,
    TagListPage,
    TagListSuccess,
)
from immersive_library.services import tags as tag_service
from immersive_library.utils import content_guard, owner_guard

router = APIRouter(tags=["Tags"])


@router.get("/v3/tag/{project}")
@public_cache()
@cache(expire=60)
async def list_project_tags_v3(
    project: str,
    limit: int = Query(
        100, ge=1, le=500, description="The maximum number of tags to fetch."
    ),
    offset: int = Query(0, ge=0, description="The offset to start fetching tags from."),
) -> TagListPage:
    rows = await tag_service.list_project_tags(project, limit + 1, offset)
    return TagListPage(
        tags=[TagCount(tag=row["tag"], count=row["count"]) for row in rows[:limit]],
        has_more=len(rows) > limit,
    )


@router.get("/v1/tag/{project}/{contentid}", response_model=TagListSuccess)
@public_cache()
@cache(expire=60)
async def list_content_tags(project: str, contentid: int) -> TagListSuccess:
    await content_guard(project, contentid)
    tags = await database.fetch_all(
        "SELECT tag FROM tags WHERE contentid=:contentid", {"contentid": contentid}
    )
    return TagListSuccess(tags=[t[0] for t in tags])


@router.post(
    "/v1/tag/{project}/{contentid}/{tag}",
    responses={401: {"model": Error}, 428: {"model": Error}},
    dependencies=[Depends(owner_guard)],
)
async def add_tag(project: str, contentid: int, tag: str) -> PlainSuccess:
    if "," in tag:
        raise HTTPException(401, "Contains invalid characters")
    if not await tag_service.set_tag(project, contentid, tag, True):
        raise HTTPException(428, "Already tagged")
    return PlainSuccess()


@router.delete(
    "/v1/tag/{project}/{contentid}/{tag}",
    responses={401: {"model": Error}, 428: {"model": Error}},
    dependencies=[Depends(owner_guard)],
)
async def delete_tag(project: str, contentid: int, tag: str) -> PlainSuccess:
    if not await tag_service.set_tag(project, contentid, tag, False):
        raise HTTPException(428, "Not tagged")
    return PlainSuccess()
