import time
from enum import Enum
from pathlib import Path
from typing import Optional, Union

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
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
    exists,
    fetch_content,
    get_base_select,
    get_lite_content_class,
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
@cache(expire=60)
async def list_content_v2(
    project: str,
    track: TrackEnum = TrackEnum.ALL,
    userid: Optional[None] = Query(
        None, description="Only include a given users submissions."
    ),
    whitelist: Optional[str] = Query(
        None,
        description="Only include content that matches every comma separated term in either the username, title, or tags.",
    ),
    blacklist: Optional[str] = Query(
        None,
        description="Exclude content that matches any comma separated term in the tags.",
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
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> ContentListSuccess:
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
        token,
        authorization,
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
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> ContentListSuccess:
    # Use me user if none is provided
    userid = userid or await token_to_userid(database, token, authorization)

    prompt = get_base_select(False, include_meta)
    values: dict[str, Union[str, int]] = {"project": project}

    # Filter for a specific track
    if track == TrackEnum.ALL:
        prompt += "\n WHERE c.project = :project"
    elif track == TrackEnum.LIKES:
        prompt += "\n INNER JOIN likes on likes.contentid=c.oid"
        prompt += "\n WHERE c.project=:project AND likes.userid=:userid"
        values["userid"] = userid
    elif track == TrackEnum.SUBMISSIONS:
        prompt += "\n WHERE c.project=:project AND c.userid=:userid"
        values["userid"] = userid
    else:
        raise HTTPException(400, "Invalid track")

    # Hide personally banned content
    if token is not None and userid is not None:
        prompt += """
         AND NOT EXISTS (SELECT *
                    FROM reports
                    WHERE reports.contentid = c.oid AND reports.reason = 'DEFAULT' AND reports.userid = :userid)
        """
        values["userid"] = userid

    # Remove content from banned users
    if filter_banned:
        prompt += "\n AND NOT users.banned"

    # Remove reported content
    if filter_reported:
        prompt += "\n AND 1.0 + likes / 10.0 - reports >= 0.0"

    # Only if all terms matches either a tag or the title, allow this content
    if whitelist:
        for index, term in enumerate(
            list(v.strip() for v in whitelist.split(",") if v.strip)
        ):
            prompt += f"\n AND (username LIKE :whitelist_term_{index} OR title LIKE :whitelist_term_{index} OR tags LIKE :whitelist_term_{index})"
            values[f"whitelist_term_{index}"] = f"%{term}%"

    # Only if no term matches a tag
    if blacklist:
        for index, term in enumerate(
            list(v.strip() for v in blacklist.split(",") if v.strip)
        ):
            prompt += f"\n AND NOT tags LIKE :blacklist_term_{index}"
            values[f"blacklist_term_{index}"] = f"%{term}%"

    # Order by
    if order == ContentOrder.RECOMMENDATIONS:
        prompt += (
            "\n ORDER BY (likes + :like_norm) * ABS(((:seed + c.oid) * 1103515245 + 12345) - 2147483648 * CAST(((:seed + c.oid) * 1103515245 + 12345) / 2147483648 AS INTEGER)) / 2147483647.0 "
            + ("DESC" if descending else "ASC")
        )
        values["seed"] = (0 if userid is None else userid) + int(time.time() / 86400)
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
    contents = [get_lite_content_class(c, include_meta, parse_meta) for c in content]

    return ContentListSuccess(contents=contents)


@router.get("/v1/content/{project}/{contentid}", response_model=ContentSuccess)
@cache(expire=60)
async def get_content(
    project: str, contentid: int, parse_meta: bool = False, version: int = 0
) -> ContentSuccess:
    assert project
    assert version is not None

    content = await fetch_content(contentid, parse_meta)

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

    await database.execute(
        "DELETE FROM content WHERE oid=:contentid",
        {"contentid": contentid},
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

    record = await database.fetch_one(
        "SELECT version FROM content WHERE oid=:contentid AND project=:project",
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

    render_url = request.url_for(
        "get_render_view", project=project, contentid=contentid
    )
    render_url = str(render_url.include_query_params(width=width, height=height))

    try:
        png_bytes = await render_headless_png(render_url, width=width, height=height)
    except Exception as exc:
        raise HTTPException(500, f"Render failed: {exc}") from exc

    tmp_path = cache_path.with_suffix(".tmp")
    tmp_path.write_bytes(png_bytes)
    tmp_path.replace(cache_path)
    return Response(content=png_bytes, media_type="image/png", headers=cache_headers)
