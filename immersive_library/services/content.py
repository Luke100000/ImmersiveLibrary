import base64
import time

import orjson
from cachetools import cached
from databases.interfaces import Record
from fastapi import HTTPException

from immersive_library.common import get_project
from immersive_library.database import database
from immersive_library.enums import ContentOrder
from immersive_library.models import Content, ContentSummary, ContentUpload
from immersive_library.services.recommendations import (
    HOT_SCORE,
    PREFERENCE_RANK,
    PREFERENCE_SEEDS,
    SIMILAR_RANK,
    SIMILAR_SEEDS,
    neighbor_scores,
    preference_strength,
    recommendation_score,
)
from immersive_library.services.reports import REPORT_SCORE
from immersive_library.services.search import RANKING_JOINS, plan_search
from immersive_library.utils import (
    DAY,
    set_tags,
    update_precomputation,
)


async def list_records(
    project: str,
    author_id: int | None = None,
    liked_by: int | None = None,
    collection_id: int | None = None,
    q: str | None = None,
    filter_banned: bool = True,
    filter_reported: bool = True,
    offset: int = 0,
    limit: int = 100,
    order: ContentOrder = ContentOrder.DATE,
    descending: bool = False,
    include_meta: bool = False,
    include_data: bool = False,
    viewer_id: int | None = None,
    recommendation_user_id: int | None = None,
    include_personal: bool = False,
    similar_to: int | None = None,
    similar_to_collection: int | None = None,
) -> list[Record]:
    if order == ContentOrder.ADDED and collection_id is None:
        raise HTTPException(400, "Added ordering requires a collection")

    # The moderation queue needs to be able to show banned or reported content
    if order == ContentOrder.REPORTS:
        filter_banned = False
        filter_reported = False

    recommended = order == ContentOrder.RECOMMENDATIONS
    similar = similar_to is not None or similar_to_collection is not None
    search = plan_search(q, rank=recommended)
    personalized = recommended and recommendation_user_id is not None

    query = get_content_select(include_meta, include_data, include_personal)
    values: dict[str, str | int | float | None] = {"project": project, **search.values}
    if include_personal:
        values["viewer_id"] = viewer_id

    ctes = []
    if personalized:
        ctes.append(
            neighbor_scores("preference", PREFERENCE_SEEDS, exclude_seeds=False)
        )
        ctes.append(PREFERENCE_RANK)
        query += "\n LEFT JOIN preference_rank ON preference_rank.content_id = c.oid"
        values["preference_user_id"] = recommendation_user_id
    if search.ranking is not None:
        ctes.append(search.ranking)
        query += RANKING_JOINS
    if similar:
        ctes.append(neighbor_scores("similar", SIMILAR_SEEDS, exclude_seeds=True))
        ctes.append(SIMILAR_RANK)
        query += "\n JOIN similar_rank ON similar_rank.content_id = c.oid"
        values["similar_to"] = similar_to
        values["similar_to_collection"] = similar_to_collection
        values["similar_viewer_id"] = viewer_id
    if ctes:
        query = "WITH " + ", ".join(ctes) + query

    if collection_id is not None:
        query += """
            JOIN collection_items AS collection_membership
                ON collection_membership.content_id=c.oid
                AND collection_membership.collection_id=:collection_id
        """

    query += "\n WHERE c.project = :project"

    if collection_id is not None:
        query += """
            AND EXISTS (
                SELECT 1 FROM collections WHERE oid=:collection_id AND project=:project
                    AND (user_id=:collection_viewer_id OR is_public=1)
            )
        """
        values["collection_id"] = collection_id
        values["collection_viewer_id"] = viewer_id

    if author_id is not None:
        query += "\n AND c.user_id = :author_id"
        values["author_id"] = author_id
    if liked_by is not None:
        query += "\n AND EXISTS (SELECT 1 FROM likes WHERE likes.content_id=c.oid AND likes.user_id=:liked_by)"
        values["liked_by"] = liked_by

    if filter_banned:
        query += "\n AND NOT users.banned"

    if filter_reported:
        query += f"\n AND {REPORT_SCORE} <= 1"
        if viewer_id is not None:
            query += """
             AND NOT EXISTS (SELECT 1 FROM reports
                WHERE reports.content_id = c.oid AND reports.reason = 'DEFAULT'
                    AND reports.user_id = :viewer_id)
            """
            values["viewer_id"] = viewer_id

    if order == ContentOrder.REPORTS:
        query += f"\n AND {REPORT_SCORE} > 1"

    for condition in search.conditions:
        query += f"\n AND {condition}"

    direction = "DESC" if descending else "ASC"

    if recommended:
        preference = None
        if personalized:
            preference = await preference_strength(project, recommendation_user_id)
        score = recommendation_score(search.ranking is not None, similar, preference)
        query += f"\n ORDER BY {score} {direction}"
        values["seed"] = (
            0 if recommendation_user_id is None else recommendation_user_id
        ) + int(time.time() / DAY)
    elif order == ContentOrder.ADDED:
        query += f"\n ORDER BY collection_membership.created_at {direction}"
    elif order == ContentOrder.REPORTS:
        query += f"\n ORDER BY {REPORT_SCORE} {direction}"
    elif order == ContentOrder.HOT:
        query += f"\n ORDER BY {HOT_SCORE} {direction}, likes {direction}"
    elif order == ContentOrder.POPULAR:
        query += (
            f"\n ORDER BY precomputation.recent_likes {direction}, likes {direction}"
        )
    else:
        sort_column = "c.oid" if order == ContentOrder.DATE else order.name
        query += f"\n ORDER BY {sort_column} {direction}"

    if order != ContentOrder.DATE:
        query += f", c.oid {direction}"

    query += "\n LIMIT :limit OFFSET :offset"
    values["limit"] = limit
    values["offset"] = offset

    return await database.fetch_all(query, values)


def summarize(
    record: Record, include_meta: bool = True, include_data: bool = False
) -> ContentSummary:
    return ContentSummary(
        content_id=record["oid"],
        user_id=record["user_id"],
        username=record["username"],
        likes=record["likes"],
        tags=orjson.loads(record["content_tags"]),
        title=record["title"],
        version=record["version"],
        meta=record["meta"] if include_meta else None,
        data=base64.b64encode(record["data"]).decode() if include_data else None,
        is_liked=bool(record["is_liked"]),
        reports=orjson.loads(record["viewer_reports"]),
    )


@cached(cache={})
def get_content_select(
    include_meta: bool, include_data: bool, include_personal: bool = False
) -> str:
    personal_fields = ""
    if include_personal:
        # Keep relationship values structured, including reasons or tags with commas.
        personal_fields = """,
            EXISTS (SELECT 1 FROM likes
                    WHERE likes.content_id=c.oid AND likes.user_id=:viewer_id) AS is_liked,
            (SELECT json_group_array(reason) FROM (
                SELECT reason FROM reports
                WHERE content_id=c.oid AND user_id=:viewer_id ORDER BY reason
            )) AS viewer_reports,
            (SELECT json_group_array(tag) FROM (
                SELECT tag FROM tags WHERE content_id=c.oid ORDER BY tag
            )) AS content_tags"""
    return f"""
        SELECT c.oid,
               c.user_id,
               users.username,
               c.title,
               c.version,
               {"c.meta," if include_meta else ""}
               {"c.data," if include_data else ""}
               precomputation.likes,
               precomputation.tags,
               precomputation.reports
               {personal_fields}
        FROM content c
            INNER JOIN users ON c.user_id = users.oid
            INNER JOIN precomputation ON c.oid = precomputation.content_id
    """


async def get_record(
    project: str,
    content_id: int,
    viewer_id: int | None = None,
    include_data: bool = False,
) -> Record:
    record = await database.fetch_one(
        get_content_select(True, include_data, True)
        + " WHERE c.oid=:content_id AND c.project=:project",
        {"project": project, "content_id": content_id, "viewer_id": viewer_id},
    )
    if record is None:
        raise HTTPException(404, "Content not found")
    return record


async def get_content(
    project: str, content_id: int, viewer_id: int | None = None
) -> Content:
    record = await get_record(project, content_id, viewer_id, include_data=True)
    return Content(**summarize(record, include_data=True).model_dump())


async def create_content(project: str, content: ContentUpload, user_id: int) -> int:
    await get_project(project).validate("pre_upload", database, user_id, content)
    async with database.transaction():
        content_id = await database.fetch_val(
            """
            INSERT INTO content (user_id, project, title, meta, data)
            SELECT :user_id, :project, :title, :meta, :data
            WHERE NOT EXISTS (
                SELECT 1 FROM content
                WHERE project=:project AND length(data)=length(:data) AND data=:data
            ) RETURNING oid
            """,
            {
                "user_id": user_id,
                "project": project,
                "title": content.title,
                "meta": content.meta,
                "data": content.payload,
            },
        )
        if content_id is None:
            raise HTTPException(428, "Duplicate found!")
        if content.tags is not None:
            await set_tags(database, content_id, content.tags)
        await get_project(project).call("post_upload", database, user_id, content_id)
        await update_precomputation(database, content_id)
    return content_id


async def update_content(
    project: str, content_id: int, content: ContentUpload, user_id: int
) -> None:
    await get_project(project).validate("pre_upload", database, user_id, content)
    async with database.transaction():
        updated = await database.fetch_val(
            """
            UPDATE content SET title=:title, meta=:meta, data=:data, version=version+1,
                updated_at=unixepoch()
            WHERE project=:project AND oid=:content_id RETURNING oid
            """,
            {
                "title": content.title,
                "meta": content.meta,
                "data": content.payload,
                "project": project,
                "content_id": content_id,
            },
        )
        if updated is None:
            raise HTTPException(404, "Content not found")
        if content.tags is not None:
            await set_tags(database, content_id, content.tags)
        await get_project(project).call("post_upload", database, user_id, content_id)
        await update_precomputation(database, content_id)


async def delete_content(project: str, content_id: int) -> None:
    async with database.transaction():
        deleted = await database.fetch_val(
            "DELETE FROM content WHERE oid=:content_id AND project=:project RETURNING oid",
            {"content_id": content_id, "project": project},
        )
        if deleted is None:
            raise HTTPException(404, "Content not found")
