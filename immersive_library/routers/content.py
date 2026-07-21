import os
import time
from enum import Enum
from pathlib import Path
from typing import Optional, Union
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request
from fastapi_cache.decorator import cache
from starlette.responses import Response

from immersive_library.common import database, get_project, projects
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
from immersive_library.rendering import render_headless_png
from immersive_library.utils import (
    SESSION_COOKIE,
    enforce_rate_limit,
    exists,
    fetch_content,
    get_base_select,
    get_lite_content_class,
    is_moderator,
    logged_in_guard,
    owner_guard,
    set_tags,
    token_to_userid,
    update_precomputation,
)

router = APIRouter(tags=["Content"])


class TrackEnum(str, Enum):
    ALL = "all"
    LIKES = "likes"
    SUBMISSIONS = "submissions"


class ContentOrder(str, Enum):
    DATE = "date"
    LIKES = "likes"
    TITLE = "title"
    REPORTS = "reports"
    RECOMMENDATIONS = "recommendations"


class RenderPreset(str, Enum):
    EMBED = "embed"
    ICON = "icon"
    THUMBNAIL = "thumbnail"
    SQUARE = "square"


RENDER_PRESET_SIZES: dict[RenderPreset, tuple[int, int]] = {
    RenderPreset.EMBED: (1200, 630),
    RenderPreset.ICON: (256, 256),
    RenderPreset.THUMBNAIL: (512, 512),
    RenderPreset.SQUARE: (1024, 1024),
}

CACHE_DIR = Path("data/cache")


@router.get(
    "/v1/content",
    response_model_exclude_none=True,
    response_model=ProjectListSuccess,
)
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
async def list_content_v2(
    project: str,
    track: TrackEnum = TrackEnum.ALL,
    userid: Optional[int] = Query(
        None, description="Only include a given users submissions."
    ),
    whitelist: Optional[str] = Query(
        None,
        description=(
            "Only include content that matches every comma-separated term. Prefix a "
            "term with @ for an exact username, # for an exact tag, or ~ for a "
            "partial title; unprefixed terms partially match username, title, or "
            "tags. Prefix any term with - to exclude it."
        ),
    ),
    blacklist: Optional[str] = Query(
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
    authorization: Optional[str] = Header(None),
    session_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE),
) -> ContentListSuccess:
    viewer_userid = await token_to_userid(database, authorization, session_token)
    return await inner_list_content_v2(
        project,
        track,
        userid,
        whitelist,
        blacklist,
        filter_banned,
        filter_reported,
        offset,
        limit,
        order,
        descending,
        include_meta,
        parse_meta,
        viewer_userid,
        False,
    )


@router.get(
    "/v3/content/{project}",
    response_model_exclude_none=True,
    response_model=ContentListSuccess,
)
async def list_content_v3(
    project: str,
    track: TrackEnum = TrackEnum.ALL,
    userid: Optional[int] = Query(
        None, description="Only include a given users submissions."
    ),
    whitelist: Optional[str] = Query(
        None,
        description=(
            "Only include content that matches every comma-separated term. Prefix a "
            "term with @ for an exact username, # for an exact tag, or ~ for a "
            "partial title; unprefixed terms partially match username, title, or "
            "tags. Prefix any term with - to exclude it."
        ),
    ),
    blacklist: Optional[str] = Query(
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
    authorization: Optional[str] = Header(None),
    session_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE),
) -> ContentListSuccess:
    viewer_userid = await token_to_userid(database, authorization, session_token)
    return await inner_list_content_v2(
        project,
        track,
        userid,
        whitelist,
        blacklist,
        filter_banned,
        filter_reported,
        offset,
        limit,
        order,
        descending,
        include_meta,
        parse_meta,
        viewer_userid,
        True,
    )


async def inner_list_content_v2(
    project: str,
    track: TrackEnum = TrackEnum.ALL,
    userid: Optional[int] = None,
    whitelist: Optional[str] = None,
    blacklist: Optional[str] = None,
    filter_banned: bool = True,
    filter_reported: bool = True,
    offset: int = 0,
    limit: int = 100,
    order: ContentOrder = ContentOrder.DATE,
    descending: bool = False,
    include_meta: bool = False,
    parse_meta: bool = False,
    viewer_userid: Optional[int] = None,
    include_liked: bool = False,
) -> ContentListSuccess:
    target_userid = userid if userid is not None else viewer_userid
    viewer_is_moderator = (
        viewer_userid is not None and await is_moderator(database, viewer_userid)
    )
    if not viewer_is_moderator:
        filter_banned = True
        filter_reported = True

    prompt = get_base_select(False, include_meta, include_liked)
    values: dict[str, Union[str, int]] = {
        "project": project,
        "viewer_userid": -1 if viewer_userid is None else viewer_userid,
    }

    # Filter for a specific track
    if track == TrackEnum.ALL:
        prompt += "\n WHERE c.project = :project"
    elif track == TrackEnum.LIKES:
        if target_userid is None:
            raise HTTPException(401, "Authentication required")
        prompt += "\n INNER JOIN likes on likes.contentid=c.oid"
        prompt += "\n WHERE c.project=:project AND likes.userid=:target_userid"
        values["target_userid"] = target_userid
    elif track == TrackEnum.SUBMISSIONS:
        if target_userid is None:
            raise HTTPException(401, "Authentication required")
        prompt += "\n WHERE c.project=:project AND c.userid=:target_userid"
        values["target_userid"] = target_userid
    else:
        raise HTTPException(400, "Invalid track")

    # Hide content personally reported by the authenticated viewer.
    if viewer_userid is not None:
        prompt += """
         AND NOT EXISTS (SELECT *
                    FROM reports
                    WHERE reports.contentid = c.oid AND reports.reason = 'DEFAULT' AND reports.userid = :viewer_userid)
        """

    # Remove content from banned users
    if filter_banned:
        prompt += "\n AND NOT users.banned"

    # Remove reported content
    if filter_reported:
        prompt += "\n AND 1.0 + likes / 10.0 - reports >= 0.0"

    whitelist_terms = (
        [v.strip() for v in whitelist.split(",") if v.strip()] if whitelist else []
    )

    # Treat the deprecated blacklist as exact excluded-tag whitelist terms.
    if blacklist:
        whitelist_terms.extend(
            f"-#{term.strip()}" for term in blacklist.split(",") if term.strip()
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

        prompt += f"\n AND {'NOT ' if negated else ''}{condition}"

    # Order by
    if order == ContentOrder.RECOMMENDATIONS:
        prompt += (
            "\n ORDER BY (likes + :like_norm) * ABS(((:seed + c.oid) * 1103515245 + 12345) - 2147483648 * CAST(((:seed + c.oid) * 1103515245 + 12345) / 2147483648 AS INTEGER)) / 2147483647.0 "
            + ("DESC" if descending else "ASC")
        )
        values["seed"] = (
            0 if viewer_userid is None else viewer_userid
        ) + int(time.time() / 86400)
        values["like_norm"] = 100
    else:
        prompt += (
            f"\n ORDER BY {'c.oid' if order == ContentOrder.DATE else order.name} "
            + ("DESC" if descending else "ASC")
        )

    # Limit
    prompt += "\n LIMIT :limit OFFSET :offset"
    values["limit"] = limit
    values["offset"] = offset

    # Fetch
    content = await database.fetch_all(prompt, values)

    # Convert to content accessors, which are more lightweight than the actual content instances
    contents = [
        get_lite_content_class(c, include_meta, parse_meta, include_liked)
        for c in content
    ]

    return ContentListSuccess(contents=contents)


@router.get("/v1/content/{project}/{contentid}", response_model=ContentSuccess)
async def get_content(
    project: str,
    contentid: int,
    parse_meta: bool = False,
    version: int = 0,
    authorization: Optional[str] = Header(None),
    session_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE),
) -> ContentSuccess:
    assert version is not None
    viewer_userid = await token_to_userid(database, authorization, session_token)
    include_hidden = viewer_userid is not None and await is_moderator(database, viewer_userid)
    content = await fetch_content(contentid, parse_meta, project, include_hidden)
    return ContentSuccess(content=content)


@router.post(
    "/v1/content/{project}",
    responses={401: {"model": Error}, 428: {"model": Error}, 400: {"model": Error}},
)
async def add_content(
    project: str, content: ContentUpload, userid: int = Depends(logged_in_guard)
) -> ContentIdSuccess:
    # Check for duplicates
    if await exists(
        database,
        "SELECT count(*) FROM content WHERE project=:project AND data=:data",
        {"project": project, "data": content.payload},
    ):
        raise HTTPException(428, "Duplicate found!")

    # Call validators for content verification
    await get_project(project).validate("pre_upload", database, userid, content)

    contentid = await database.execute(
        "INSERT INTO content (userid, project, title, meta, data) VALUES(:userid, :project, :title, :meta, :data)",
        {
            "userid": userid,
            "project": project,
            "title": content.title,
            "meta": content.meta,
            "data": content.payload,
        },
    )

    if content.tags is not None:
        await set_tags(database, contentid, content.tags)

    # Call validators for eventual post-processing
    await get_project(project).call("post_upload", database, userid, contentid)

    await update_precomputation(database, contentid)

    return ContentIdSuccess(contentid=contentid)


@router.put("/v1/content/{project}/{contentid}", responses={401: {"model": Error}})
async def update_content(
    project: str,
    contentid: int,
    content: ContentUpload,
    userid: int = Depends(owner_guard),
) -> PlainSuccess:
    # Call validators for content verification
    await get_project(project).validate("pre_upload", database, userid, content)

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

    return PlainSuccess()


@router.delete("/v1/content/{project}/{contentid}", responses={401: {"model": Error}})
async def delete_content(
    project: str, contentid: int, userid: int = Depends(owner_guard)
) -> PlainSuccess:
    assert project
    assert userid

    async with database.transaction():
        for table in ("likes", "reports", "tags", "precomputation"):
            await database.execute(
                f"DELETE FROM {table} WHERE contentid=:contentid",
                {"contentid": contentid},
            )
        await database.execute(
            "DELETE FROM content WHERE oid=:contentid AND project=:project",
            {"contentid": contentid, "project": project},
        )

    return PlainSuccess()


@router.get("/v1/render/{project}/{contentid}", response_class=Response)
async def render_content_png(
    request: Request,
    project: str,
    contentid: int,
    preset: RenderPreset = Query(RenderPreset.EMBED),
) -> Response:
    if project not in projects:
        raise HTTPException(404, "Project not found")

    await enforce_rate_limit(request, "render", 30, 60)
    record = await database.fetch_one(
        """
        SELECT c.version
        FROM content c
        INNER JOIN users ON users.oid = c.userid
        INNER JOIN precomputation ON precomputation.contentid = c.oid
        WHERE c.oid=:contentid AND c.project=:project
          AND NOT users.banned
          AND 1.0 + precomputation.likes / 10.0 - precomputation.reports >= 0.0
        """,
        {"contentid": contentid, "project": project},
    )
    if record is None:
        raise HTTPException(404, "Content not found")

    width, height = RENDER_PRESET_SIZES[preset]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_name = f"{contentid}_{record['version']}_{width}x{height}.png"
    cache_path = CACHE_DIR / cache_name
    cache_headers = {
        "Cache-Control": "public, max-age=86400, s-maxage=86400, immutable",
    }
    if cache_path.exists():
        return Response(
            content=cache_path.read_bytes(),
            media_type="image/png",
            headers=cache_headers,
        )

    render_base_url = os.getenv("RENDER_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    render_url = (
        f"{render_base_url}/render/{quote(project, safe='')}/{contentid}"
        f"?width={width}&height={height}"
    )

    try:
        png_bytes = await render_headless_png(render_url, width=width, height=height)
    except Exception as exc:
        raise HTTPException(500, "Render failed") from exc

    tmp_path = cache_path.with_suffix(".tmp")
    tmp_path.write_bytes(png_bytes)
    tmp_path.replace(cache_path)
    return Response(content=png_bytes, media_type="image/png", headers=cache_headers)
