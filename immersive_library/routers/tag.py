from fastapi import APIRouter, Depends, HTTPException
from fastapi_cache.decorator import cache

from immersive_library.common import database
from immersive_library.models import (
    Error,
    PlainSuccess,
    TagDictSuccess,
    TagListSuccess,
)
from immersive_library.utils import (
    PROTECTED_TAGS,
    has_tag,
    is_moderator,
    owner_guard,
    update_precomputation,
)

router = APIRouter(tags=["Tags"])


@router.get("/v1/tag/{project}", response_model=TagDictSuccess)
@cache(expire=60)
async def list_project_tags(
    project: str, limit: int = 100, offset: int = 0
) -> TagDictSuccess:
    rows = await database.fetch_all(
        """
        SELECT tag, COUNT(*) as count
        FROM tags
        INNER JOIN content ON tags.contentid = content.oid
        WHERE content.project = :project
        GROUP BY tag
        ORDER BY count DESC
        LIMIT :limit
        OFFSET :offset
        """,
        {"project": project, "limit": limit, "offset": offset},
    )

    return TagDictSuccess(tags={row["tag"]: row["count"] for row in rows})


@router.get("/v1/tag/{project}/{contentid}", response_model=TagListSuccess)
@cache(expire=60)
async def list_content_tags(project: str, contentid: int) -> TagListSuccess:
    tags = await database.fetch_all(
        """
        SELECT tags.tag
        FROM tags
        INNER JOIN content ON content.oid = tags.contentid
        WHERE tags.contentid=:contentid AND content.project=:project
        """,
        {"contentid": contentid, "project": project},
    )
    return TagListSuccess(tags=[t[0] for t in tags])


@router.post(
    "/v1/tag/{project}/{contentid}/{tag}",
    responses={401: {"model": Error}, 428: {"model": Error}},
)
async def add_tag(
    project: str, contentid: int, tag: str, userid: int = Depends(owner_guard)
) -> PlainSuccess:
    if not 1 <= len(tag) <= 64 or "," in tag:
        raise HTTPException(400, "Invalid tag")
    if tag in PROTECTED_TAGS and not await is_moderator(database, userid):
        raise HTTPException(403, "Protected tag")

    if await has_tag(database, contentid, tag):
        raise HTTPException(428, "Already tagged")

    await database.execute(
        "INSERT OR IGNORE INTO tags (contentid, tag) VALUES(:contentid, :tag)",
        {"contentid": contentid, "tag": tag},
    )

    await update_precomputation(database, contentid)

    return PlainSuccess()


@router.delete(
    "/v1/tag/{project}/{contentid}/{tag}",
    responses={401: {"model": Error}, 428: {"model": Error}},
)
async def delete_tag(
    project: str, contentid: int, tag: str, userid: int = Depends(owner_guard)
) -> PlainSuccess:
    if tag in PROTECTED_TAGS and not await is_moderator(database, userid):
        raise HTTPException(403, "Protected tag")

    if not await has_tag(database, contentid, tag):
        raise HTTPException(428, "Not tagged")

    await database.execute(
        "DELETE FROM tags WHERE contentid=:contentid AND tag=:tag",
        {"contentid": contentid, "tag": tag},
    )

    await update_precomputation(database, contentid)

    return PlainSuccess()
