import base64
from typing import Any

import orjson
from databases.interfaces import Record
from fastapi import HTTPException

from immersive_library.enums import ContentOrder, ContentTrack
from immersive_library.routers.deprecated.models import (
    Content,
    ContentListSuccess,
    LiteContent,
    LiteUser,
)
from immersive_library.services import content as content_service


def safe_parse(meta: str) -> dict[str, Any]:
    try:
        parsed_meta = orjson.loads(meta)
    except orjson.JSONDecodeError:
        return {}

    return parsed_meta if isinstance(parsed_meta, dict) else {}


def get_lite_user_class(record: Record) -> LiteUser:
    return LiteUser(
        userid=record["oid"],
        username=record["username"],
        submission_count=record["submission_count"],
        likes_given=record["likes_given"],
        likes_received=record["likes_received"],
        moderator=record["moderator"] > 0,
    )


def get_lite_content_class(
    record: Record, include_meta: bool, parse_meta: bool
) -> LiteContent:
    """
    Populates a lite content object
    """
    meta = None
    if include_meta:
        meta = safe_parse(record["meta"]) if parse_meta else record["meta"]

    return LiteContent(
        contentid=record["oid"],
        userid=record["user_id"],
        username=record["username"],
        likes=record["likes"],
        tags=record["tags"].split(",") if record["tags"] else [],
        title=record["title"],
        version=record["version"],
        meta=meta,
    )


def get_content_class(record: Record, parse_meta: bool = True) -> Content:
    """
    Populates a content object
    """
    return Content(
        contentid=record["oid"],
        userid=record["user_id"],
        username=record["username"],
        likes=record["likes"],
        tags=record["tags"].split(",") if record["tags"] else [],
        title=record["title"],
        version=record["version"],
        meta=safe_parse(record["meta"]) if parse_meta else record["meta"],
        data=base64.b64encode(record["data"]).decode("utf-8"),
    )


async def list_content(
    project: str,
    track: ContentTrack = ContentTrack.ALL,
    user_id: int | None = None,
    whitelist: str | None = None,
    filter_banned: bool = True,
    filter_reported: bool = True,
    offset: int = 0,
    limit: int = 100,
    order: ContentOrder = ContentOrder.DATE,
    descending: bool = False,
    include_meta: bool = False,
    parse_meta: bool = False,
    viewer_id: int | None = None,
) -> ContentListSuccess:
    target_user = user_id if user_id is not None else viewer_id
    author_id = None
    liked_by = None
    if track == ContentTrack.LIKES:
        liked_by = target_user
    elif track == ContentTrack.SUBMISSIONS:
        author_id = target_user
    elif track != ContentTrack.ALL:
        raise HTTPException(400, "Invalid track")
    if track != ContentTrack.ALL and target_user is None:
        return ContentListSuccess(contents=[])

    records = await content_service.list_records(
        project,
        author_id=author_id,
        liked_by=liked_by,
        q=whitelist,
        filter_banned=filter_banned,
        filter_reported=filter_reported,
        offset=offset,
        limit=limit,
        order=order,
        descending=descending,
        include_meta=include_meta,
        viewer_id=viewer_id,
        recommendation_user_id=target_user,
    )
    return ContentListSuccess(
        contents=[
            get_lite_content_class(row, include_meta, parse_meta) for row in records
        ]
    )
