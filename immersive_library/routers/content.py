from fastapi import APIRouter, Depends, Header, Query
from fastapi_cache.decorator import cache

from immersive_library.caching import public_cache
from immersive_library.database import database
from immersive_library.models import (
    ContentIdSuccess,
    ContentListSuccess,
    ContentSuccess,
    ContentUpload,
    Error,
    PlainSuccess,
    ProjectListSuccess,
    ProjectSummary,
)
from immersive_library.routers.deprecated.filters import merge_tag_filters
from immersive_library.services import content as content_service
from immersive_library.utils import (
    fetch_content,
    logged_in_guard,
    owner_guard,
    token_to_userid,
)

router = APIRouter(tags=["Content"])


@router.get(
    "/v1/content",
    response_model_exclude_none=True,
    response_model=ProjectListSuccess,
)
@public_cache()
@cache(expire=300)
async def list_projects() -> ProjectListSuccess:
    all_projects = await database.fetch_all(
        "SELECT project, count(*) as content_count FROM content GROUP BY project ORDER BY project"
    )
    return ProjectListSuccess(
        projects=[
            ProjectSummary(name=p["project"], content_count=p["content_count"])
            for p in all_projects
        ]
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
    track: content_service.TrackEnum = content_service.TrackEnum.ALL,
    userid: int | None = Query(
        None,
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
    order: content_service.ContentOrder = content_service.ContentOrder.DATE,
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
    viewer_id = await token_to_userid(database, token, authorization)

    return await content_service.list_content(
        project,
        track=track,
        userid=userid,
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
    project: str, contentid: int, parse_meta: bool = False, version: int = 0
) -> ContentSuccess:
    assert project
    assert version is not None

    content = await fetch_content(project, contentid, parse_meta)

    return ContentSuccess(content=content)


@router.post(
    "/v1/content/{project}",
    responses={401: {"model": Error}, 428: {"model": Error}, 400: {"model": Error}},
)
async def add_content(
    project: str, content: ContentUpload, userid: int = Depends(logged_in_guard)
) -> ContentIdSuccess:
    contentid = await content_service.create_content(project, content, userid)
    return ContentIdSuccess(contentid=contentid)


@router.put("/v1/content/{project}/{contentid}", responses={401: {"model": Error}})
async def update_content(
    project: str,
    contentid: int,
    content: ContentUpload,
    userid: int = Depends(owner_guard),
) -> PlainSuccess:
    await content_service.update_content(project, contentid, content, userid)
    return PlainSuccess()


@router.delete("/v1/content/{project}/{contentid}", responses={401: {"model": Error}})
async def delete_content(
    project: str, contentid: int, userid: int = Depends(owner_guard)
) -> PlainSuccess:
    assert project
    assert userid

    await content_service.delete_content(contentid)
    return PlainSuccess()
