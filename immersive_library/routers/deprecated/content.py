from typing import Annotated

from fastapi import APIRouter, Header, Path, Query
from fastapi_cache.decorator import cache

from immersive_library.caching import public_cache
from immersive_library.database import database
from immersive_library.enums import ContentOrder, ContentTrack
from immersive_library.routers.deprecated import serialization as legacy_content
from immersive_library.routers.deprecated.filters import merge_tag_filters
from immersive_library.routers.deprecated.models import (
    ContentListSuccess,
    ContentSuccess,
)
from immersive_library.services import content as content_service
from immersive_library.utils import (
    token_to_user_id,
)

router = APIRouter(tags=["Content"], deprecated=True)


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
    return await legacy_content.list_content(
        project,
        whitelist=merge_tag_filters(
            None if invert_filter else tag_filter,
            tag_filter if invert_filter else None,
        ),
        limit=500,
    )


@router.get(
    "/v2/content/{project}",
    response_model_exclude_none=True,
    response_model=ContentListSuccess,
)
@public_cache(
    when=lambda request: (
        request.query_params.get("track", "all") == "all"
        and "userid" not in request.query_params
    )
)
@cache(expire=60)
async def list_content_v2(
    project: str,
    track: ContentTrack = ContentTrack.ALL,
    user_id: int | None = Query(
        None,
        alias="userid",
        description=(
            "User context for likes, submissions and recommendation ordering. "
            "Defaults to the authenticated user."
        ),
    ),
    whitelist: str | None = Query(
        None,
        description=(
            "Only include content that matches every comma-separated term. Prefix a "
            "term with @ for an exact username, # for an exact tag, or ~ for a "
            "partial title; unprefixed terms partially match username, title, or "
            "tags. Prefix any term with - to exclude it."
        ),
    ),
    blacklist: str | None = Query(
        None,
        deprecated=True,
        description=(
            "Deprecated: use -#tag in whitelist instead. "
            "Each blacklist term is treated as -#tag."
        ),
    ),
    filter_banned: bool = Query(True, description="Exclude content from banned users."),
    filter_reported: bool = Query(
        True, description="Exclude content which has been reported by several users."
    ),
    offset: int = Query(
        0, ge=0, description="The offset to start fetching content from."
    ),
    limit: int = Query(
        10, ge=1, le=500, description="The maximum amount of content to fetch."
    ),
    order: ContentOrder = ContentOrder.DATE,
    descending: bool = False,
    include_meta: bool = Query(
        False, description="Include the meta field in the response."
    ),
    parse_meta: bool = Query(
        False,
        description="Parse the meta field and return it as a dict rather than a JSON encoded string.",
    ),
    token: str | None = None,
    authorization: str = Header(None),
) -> ContentListSuccess:
    viewer_id = await token_to_user_id(database, token, authorization)

    return await legacy_content.list_content(
        project,
        track=track,
        user_id=user_id,
        whitelist=merge_tag_filters(whitelist, blacklist),
        filter_banned=filter_banned,
        filter_reported=filter_reported,
        offset=offset,
        limit=limit,
        order=order,
        descending=descending,
        include_meta=include_meta,
        parse_meta=parse_meta,
        viewer_id=viewer_id,
    )


@router.get("/v1/content/{project}/{contentid}", response_model=ContentSuccess)
@public_cache()
@cache(expire=60)
async def get_content(
    project: str,
    content_id: Annotated[int, Path(alias="contentid")],
    parse_meta: bool = False,
    version: int = 0,
) -> ContentSuccess:
    assert project
    assert version is not None

    record = await content_service.get_record(project, content_id, include_data=True)
    content = legacy_content.get_content_class(record, parse_meta)

    return ContentSuccess(content=content)
