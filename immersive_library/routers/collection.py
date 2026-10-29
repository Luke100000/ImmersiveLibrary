from typing import Annotated

from fastapi import APIRouter, Depends, Query

from immersive_library.dependencies import (
    UserFilter,
    optional_user_id,
    resolve_user_filter,
)
from immersive_library.models import (
    CollectionCreate,
    CollectionListSuccess,
    CollectionSuccess,
    CollectionUpdate,
    Error,
    PlainSuccess,
)
from immersive_library.ratelimit import INTERACT
from immersive_library.services import collections as collection_service
from immersive_library.utils import logged_in_guard

router = APIRouter(
    tags=["Collections"],
    responses={401: {"model": Error}, 403: {"model": Error}, 404: {"model": Error}},
)


@router.get("/v1/collection/{project}", response_model_exclude_none=True)
async def list_collections(
    project: str,
    user_id: UserFilter | None = Query(
        None, description="Filter by owner; use 'me' for your collections."
    ),
    q: str | None = Query(
        None, description="Search collection titles, descriptions, and owner names."
    ),
    content_id: int | None = Query(
        None, ge=1, description="Include membership flags for this content ID."
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    viewer_id: Annotated[int | None, Depends(optional_user_id)] = None,
) -> CollectionListSuccess:
    owner_id = resolve_user_filter(user_id, viewer_id)
    collections = await collection_service.list_collections(
        project,
        user_id=owner_id,
        q=q,
        content_id=content_id,
        limit=limit + 1,
        offset=offset,
        viewer_id=viewer_id,
    )
    return CollectionListSuccess(
        collections=collections[:limit], has_more=len(collections) > limit
    )


@router.post(
    "/v1/collection/{project}",
    status_code=201,
    response_model_exclude_none=True,
    dependencies=[Depends(INTERACT)],
)
async def create_collection(
    project: str,
    collection: CollectionCreate,
    user_id: Annotated[int, Depends(logged_in_guard)],
) -> CollectionSuccess:
    return CollectionSuccess(
        collection=await collection_service.create_collection(
            project, collection, user_id
        )
    )


@router.get(
    "/v1/collection/{project}/{collection_id}", response_model_exclude_none=True
)
async def get_collection(
    project: str,
    collection_id: int,
    viewer_id: Annotated[int | None, Depends(optional_user_id)] = None,
) -> CollectionSuccess:
    return CollectionSuccess(
        collection=await collection_service.get_collection(
            project, collection_id, viewer_id
        )
    )


@router.patch(
    "/v1/collection/{project}/{collection_id}",
    response_model_exclude_none=True,
    dependencies=[Depends(INTERACT)],
)
async def update_collection(
    project: str,
    collection_id: int,
    changes: CollectionUpdate,
    user_id: Annotated[int, Depends(logged_in_guard)],
) -> CollectionSuccess:
    return CollectionSuccess(
        collection=await collection_service.update_collection(
            project, collection_id, changes, user_id
        )
    )


@router.delete(
    "/v1/collection/{project}/{collection_id}", dependencies=[Depends(INTERACT)]
)
async def delete_collection(
    project: str,
    collection_id: int,
    user_id: Annotated[int, Depends(logged_in_guard)],
) -> PlainSuccess:
    await collection_service.delete_collection(project, collection_id, user_id)
    return PlainSuccess()


@router.put(
    "/v1/collection/{project}/{collection_id}/content/{content_id}",
    dependencies=[Depends(INTERACT)],
)
async def add_content(
    project: str,
    collection_id: int,
    content_id: int,
    user_id: Annotated[int, Depends(logged_in_guard)],
) -> PlainSuccess:
    await collection_service.set_membership(
        project, collection_id, content_id, user_id, True
    )
    return PlainSuccess()


@router.delete(
    "/v1/collection/{project}/{collection_id}/content/{content_id}",
    dependencies=[Depends(INTERACT)],
)
async def remove_content(
    project: str,
    collection_id: int,
    content_id: int,
    user_id: Annotated[int, Depends(logged_in_guard)],
) -> PlainSuccess:
    await collection_service.set_membership(
        project, collection_id, content_id, user_id, False
    )
    return PlainSuccess()
