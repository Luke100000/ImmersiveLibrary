from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi_cache.decorator import cache

from immersive_library.caching import public_cache
from immersive_library.database import database
from immersive_library.dependencies import (
    UserFilter,
    optional_user_id,
    resolve_user_filter,
)
from immersive_library.enums import ContentOrder
from immersive_library.models import (
    ContentListSuccess,
    ContentSuccess,
    ContentUpload,
    Error,
    PlainSuccess,
    ProjectListSuccess,
    ProjectSummary,
)
from immersive_library.routers.deprecated.models import ContentIdSuccess
from immersive_library.services import content as content_service
from immersive_library.utils import logged_in_guard, owner_guard

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
    "/v3/content/{project}",
    response_model=ContentListSuccess,
    response_model_exclude_none=True,
)
@public_cache()
@cache(expire=60)
async def list_content(
    project: str,
    author_id: UserFilter | None = Query(
        None,
        description="Only include content authored by this user ID.",
    ),
    liked_by: UserFilter | None = Query(
        None,
        description="Only include content liked by this user ID.",
    ),
    collection_id: int | None = Query(
        None, description="Only include content in this accessible collection."
    ),
    q: str | None = Query(
        None,
        description=(
            "Only include content that matches every comma-separated term. Prefix a "
            "term with @ for an exact username, # for an exact tag, or ~ for words "
            "in the title; unprefixed terms match words in username, title, or tags. "
            "Words match from their start. Prefix any term with - to exclude it."
        ),
    ),
    similar_to: int | None = Query(
        None, description="Only include content similar to this content ID."
    ),
    similar_to_collection: int | None = Query(
        None,
        description="Only include content similar to this accessible collection.",
    ),
    filter_banned: bool = Query(True, description="Exclude content from banned users."),
    filter_reported: bool = Query(
        True,
        description="Exclude content hidden by its reports, and content you reported.",
    ),
    order: ContentOrder = ContentOrder.DATE,
    descending: bool = Query(False, description="Sort in descending order."),
    offset: int = Query(
        0, ge=0, description="The offset to start fetching content from."
    ),
    limit: int = Query(
        10, ge=1, le=500, description="The maximum amount of content to fetch."
    ),
    include_meta: bool = Query(
        False,
        description="Include the stored metadata string in each list item.",
    ),
    include_data: bool = Query(
        False,
        description="Include the Base64 content data in each list item.",
    ),
    viewer_id: Annotated[int | None, Depends(optional_user_id)] = None,
) -> ContentListSuccess:
    records = await content_service.list_records(
        project,
        author_id=resolve_user_filter(author_id, viewer_id),
        liked_by=resolve_user_filter(liked_by, viewer_id),
        collection_id=collection_id,
        q=q,
        similar_to=similar_to,
        similar_to_collection=similar_to_collection,
        filter_banned=filter_banned,
        filter_reported=filter_reported,
        order=order,
        descending=descending,
        offset=offset,
        limit=limit + 1,
        include_meta=include_meta,
        include_data=include_data,
        viewer_id=viewer_id,
        recommendation_user_id=viewer_id,
        include_personal=True,
    )
    return ContentListSuccess(
        contents=[
            content_service.summarize(row, include_meta, include_data)
            for row in records[:limit]
        ],
        has_more=len(records) > limit,
    )


@router.get("/v3/content/{project}/{content_id}", response_model=ContentSuccess)
@public_cache()
@cache(expire=60)
async def get_content_v3(
    project: str,
    content_id: int,
    viewer_id: Annotated[int | None, Depends(optional_user_id)] = None,
) -> ContentSuccess:
    return ContentSuccess(
        content=await content_service.get_content(project, content_id, viewer_id)
    )


@router.post(
    "/v1/content/{project}",
    responses={401: {"model": Error}, 428: {"model": Error}, 400: {"model": Error}},
)
async def add_content(
    project: str, content: ContentUpload, user_id: int = Depends(logged_in_guard)
) -> ContentIdSuccess:
    content_id = await content_service.create_content(project, content, user_id)
    return ContentIdSuccess(contentid=content_id)


@router.put("/v1/content/{project}/{content_id}", responses={401: {"model": Error}})
async def update_content(
    project: str,
    content_id: int,
    content: ContentUpload,
    user_id: int = Depends(owner_guard),
) -> PlainSuccess:
    await content_service.update_content(project, content_id, content, user_id)
    return PlainSuccess()


@router.delete(
    "/v1/content/{project}/{content_id}",
    responses={401: {"model": Error}},
    dependencies=[Depends(owner_guard)],
)
async def delete_content(project: str, content_id: int) -> PlainSuccess:
    await content_service.delete_content(project, content_id)
    return PlainSuccess()
