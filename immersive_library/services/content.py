import time

from fastapi import HTTPException

from immersive_library.common import get_project
from immersive_library.database import database
from immersive_library.enums import ContentOrder, TrackEnum
from immersive_library.models import ContentListSuccess, ContentUpload
from immersive_library.utils import (
    get_base_select,
    get_lite_content_class,
    set_tags,
    update_precomputation,
)


async def list_content(
    project: str,
    track: TrackEnum = TrackEnum.ALL,
    userid: int | None = None,
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
    userid = userid if userid is not None else viewer_id

    query = get_base_select(include_data=False, include_meta=include_meta)
    values: dict[str, str | int | None] = {"project": project}

    # Filter for a specific track
    if track == TrackEnum.ALL:
        query += "\n WHERE c.project = :project"
    elif track == TrackEnum.LIKES:
        query += "\n INNER JOIN likes on likes.contentid=c.oid"
        query += "\n WHERE c.project=:project AND likes.userid=:userid"
        values["userid"] = userid
    elif track == TrackEnum.SUBMISSIONS:
        query += "\n WHERE c.project=:project AND c.userid=:userid"
        values["userid"] = userid
    else:
        raise HTTPException(400, "Invalid track")

    # Hide content reported by the viewer.
    if viewer_id is not None:
        query += """
         AND NOT EXISTS (SELECT *
                    FROM reports
                    WHERE reports.contentid = c.oid AND reports.reason = 'DEFAULT' AND reports.userid = :viewer_id)
        """
        values["viewer_id"] = viewer_id

    # Remove content from banned users
    if filter_banned:
        query += "\n AND NOT users.banned"

    # Remove reported content
    if filter_reported:
        query += "\n AND 1.0 + likes / 10.0 - reports >= 0.0"

    whitelist_terms = (
        [term.strip() for term in whitelist.split(",") if term.strip()]
        if whitelist
        else []
    )

    # Only allow content that matches every whitelist term.
    for index, term in enumerate(whitelist_terms):
        parameter = f"whitelist_term_{index}"
        negated = term.startswith("-")
        search_term = term[1:].strip() if negated else term

        if search_term.startswith("@"):
            condition = f"username = :{parameter}"
            values[parameter] = search_term[1:].strip()
        elif search_term.startswith("#"):
            condition = f"""EXISTS (
                    SELECT 1 FROM tags AS whitelist_tags_{index}
                    WHERE whitelist_tags_{index}.contentid = c.oid
                    AND whitelist_tags_{index}.tag = :{parameter}
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
        values["seed"] = (0 if userid is None else userid) + int(time.time() / 86400)
        values["like_norm"] = 100
    else:
        sort_column = "c.oid" if order == ContentOrder.DATE else order.name
        query += f"\n ORDER BY {sort_column} {direction}"

    query += "\n LIMIT :limit OFFSET :offset"
    values["limit"] = limit
    values["offset"] = offset

    content = await database.fetch_all(query, values)

    contents = [
        get_lite_content_class(record, include_meta, parse_meta) for record in content
    ]

    return ContentListSuccess(contents=contents)


async def create_content(project: str, content: ContentUpload, userid: int) -> int:
    await get_project(project).validate("pre_upload", database, userid, content)

    async with database.transaction():
        contentid = await database.fetch_val(
            """
            INSERT INTO content (userid, project, title, meta, data)
            SELECT :userid, :project, :title, :meta, :data
            WHERE NOT EXISTS (
                SELECT 1 FROM content WHERE project=:project AND data=:data
            )
            RETURNING oid
            """,
            {
                "userid": userid,
                "project": project,
                "title": content.title,
                "meta": content.meta,
                "data": content.payload,
            },
        )

        if contentid is None:
            raise HTTPException(428, "Duplicate found!")

        if content.tags is not None:
            await set_tags(database, contentid, content.tags)

        # Call validators for eventual post-processing
        await get_project(project).call("post_upload", database, userid, contentid)

        await update_precomputation(database, contentid)

    return contentid


async def update_content(
    project: str, contentid: int, content: ContentUpload, userid: int
) -> None:
    await get_project(project).validate("pre_upload", database, userid, content)

    async with database.transaction():
        await database.execute(
            "UPDATE content SET title=:title, meta=:meta, data=:data, version=version+1 WHERE project=:project AND oid=:oid",
            {
                "title": content.title,
                "meta": content.meta,
                "data": content.payload,
                "project": project,
                "oid": contentid,
            },
        )

        if content.tags is not None:
            await set_tags(database, contentid, content.tags)

        # Call validators for eventual post-processing
        await get_project(project).call("post_upload", database, userid, contentid)

        await update_precomputation(database, contentid)


async def delete_content(contentid: int) -> None:
    await database.execute(
        "DELETE FROM content WHERE oid=:contentid",
        {"contentid": contentid},
    )
