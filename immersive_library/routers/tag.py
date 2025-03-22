from typing import Optional

from fastapi import HTTPException, Header, APIRouter
from fastapi_cache.decorator import cache

from immersive_library.common import database
from immersive_library.models import (
    PlainSuccess,
    Error,
    TagListSuccess,
    TagDictSuccess,
)
from immersive_library.utils import (
    token_to_userid,
    owns_content,
    has_tag,
    is_moderator,
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
    assert project
    tags = await database.fetch_all(
        "SELECT tag FROM tags WHERE contentid=:contentid", {"contentid": contentid}
    )
    return TagListSuccess(tags=[t[0] for t in tags])


@router.post(
    "/v1/tag/{project}/{contentid}/{tag}",
    responses={401: {"model": Error}, 428: {"model": Error}},
)
async def add_tag(
    project: str,
    contentid: int,
    tag: str,
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> PlainSuccess:
    assert project
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if not await owns_content(database, contentid, userid) and not await is_moderator(
        database, userid
    ):
        raise HTTPException(401, "Not your content")

    if "," in tag:
        raise HTTPException(401, "Contains invalid characters")

    if await has_tag(database, contentid, tag):
        raise HTTPException(428, "Already tagged")

    await database.execute(
        "INSERT INTO tags (contentid, tag) VALUES(:contentid, :tag)",
        {"contentid": contentid, "tag": tag},
    )

    await update_precomputation(database, contentid)

    return PlainSuccess()


@router.delete(
    "/v1/tag/{project}/{contentid}/{tag}",
    responses={401: {"model": Error}, 428: {"model": Error}},
)
async def delete_tag(
    project: str,
    contentid: int,
    tag: str,
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> PlainSuccess:
    assert project
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if not await owns_content(database, contentid, userid) and not await is_moderator(
        database, userid
    ):
        raise HTTPException(401, "Not your content")

    if not await has_tag(database, contentid, tag):
        raise HTTPException(428, "Not tagged")

    await database.execute(
        "DELETE FROM tags WHERE contentid=:contentid AND tag=:tag",
        {"contentid": contentid, "tag": tag},
    )

    await update_precomputation(database, contentid)

    return PlainSuccess()
