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
from immersive_library.utils import (
    set_tags,
    update_precomputation,
)


async def list_records(
    project: str,
    author_id: int | None = None,
    liked_by: int | None = None,
    q: str | None = None,
    filter_banned: bool = True,
    filter_reported: bool = True,
    offset: int = 0,
    limit: int = 100,
    order: ContentOrder = ContentOrder.DATE,
    descending: bool = False,
    include_meta: bool = False,
    viewer_id: int | None = None,
    recommendation_user_id: int | None = None,
    include_personal: bool = False,
) -> list[Record]:
    query = get_content_select(False, include_meta, include_personal)
    values: dict[str, str | int | None] = {"project": project}
    if include_personal:
        values["viewer_id"] = viewer_id

    query += "\n WHERE c.project = :project"
    if author_id is not None:
        query += "\n AND c.user_id = :author_id"
        values["author_id"] = author_id
    if liked_by is not None:
        query += "\n AND EXISTS (SELECT 1 FROM likes WHERE likes.content_id=c.oid AND likes.user_id=:liked_by)"
        values["liked_by"] = liked_by

    # Hide content reported by the viewer.
    if viewer_id is not None:
        query += """
         AND NOT EXISTS (SELECT *
                    FROM reports
                    WHERE reports.content_id = c.oid AND reports.reason = 'DEFAULT' AND reports.user_id = :viewer_id)
        """
        values["viewer_id"] = viewer_id

    # Remove content from banned users
    if filter_banned:
        query += "\n AND NOT users.banned"

    # Remove reported content
    if filter_reported:
        query += "\n AND 1.0 + likes / 10.0 - reports >= 0.0"

    terms = [term.strip() for term in (q or "").split(",") if term.strip()]

    for index, term in enumerate(terms):
        parameter = f"term_{index}"
        negated = term.startswith("-")
        search_term = term[1:].strip() if negated else term

        if search_term.startswith("@"):
            condition = f"username = :{parameter}"
            values[parameter] = search_term[1:].strip()
        elif search_term.startswith("#"):
            condition = f"""EXISTS (
                    SELECT 1 FROM tags
                    WHERE tags.content_id = c.oid AND tags.tag = :{parameter}
                )"""
            values[parameter] = search_term[1:].strip()
        elif search_term.startswith("~"):
            condition = f"title LIKE :{parameter}"
            values[parameter] = f"%{search_term[1:].strip()}%"
        else:
            condition = (
                f"(username LIKE :{parameter} OR title LIKE :{parameter} "
                f"OR tags LIKE :{parameter})"
            )
            values[parameter] = f"%{search_term}%"

        query += f"\n AND {'NOT ' if negated else ''}{condition}"

    direction = "DESC" if descending else "ASC"

    if order == ContentOrder.RECOMMENDATIONS:
        query += f"""
            ORDER BY (likes + :like_norm) * ABS(
                ((:seed + c.oid) * 1103515245 + 12345)
                - 2147483648 * CAST(
                    ((:seed + c.oid) * 1103515245 + 12345) / 2147483648 AS INTEGER
                )
            ) / 2147483647.0 {direction}
        """
        values["seed"] = (
            0 if recommendation_user_id is None else recommendation_user_id
        ) + int(time.time() / 86400)
        values["like_norm"] = 100
    else:
        sort_column = "c.oid" if order == ContentOrder.DATE else order.name
        query += f"\n ORDER BY {sort_column} {direction}"

    if order != ContentOrder.DATE:
        query += f", c.oid {direction}"

    query += "\n LIMIT :limit OFFSET :offset"
    values["limit"] = limit
    values["offset"] = offset

    return await database.fetch_all(query, values)


def summarize(record: Record, include_meta: bool = True) -> ContentSummary:
    return ContentSummary(
        content_id=record["oid"],
        user_id=record["user_id"],
        username=record["username"],
        likes=record["likes"],
        tags=orjson.loads(record["content_tags"]),
        title=record["title"],
        version=record["version"],
        meta=record["meta"] if include_meta else None,
        is_liked=bool(record["is_liked"]),
        reports=orjson.loads(record["viewer_reports"]),
    )


@cached(cache={})
def get_content_select(
    include_data: bool, include_meta: bool, include_personal: bool = False
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
        get_content_select(include_data, True, True)
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
    return Content(
        **summarize(record).model_dump(),
        data=base64.b64encode(record["data"]).decode("utf-8"),
    )


async def create_content(project: str, content: ContentUpload, user_id: int) -> int:
    await get_project(project).validate("pre_upload", database, user_id, content)
    async with database.transaction():
        content_id = await database.fetch_val(
            """
            INSERT INTO content (user_id, project, title, meta, data)
            SELECT :user_id, :project, :title, :meta, :data
            WHERE NOT EXISTS (
                SELECT 1 FROM content WHERE project=:project AND data=:data
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
            UPDATE content SET title=:title, meta=:meta, data=:data, version=version+1
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
