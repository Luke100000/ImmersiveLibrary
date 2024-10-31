import base64
import os
import shutil
from contextlib import asynccontextmanager

from prometheus_client import CollectorRegistry, multiprocess
from pydantic import BaseModel
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from typing_extensions import TypeVar

# Setup prometheus for multiprocessing
prom_dir = (
    os.environ["PROMETHEUS_MULTIPROC_DIR"]
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ
    else None
)
if prom_dir is not None:
    shutil.rmtree(prom_dir, ignore_errors=True)
    os.makedirs(prom_dir, exist_ok=True)
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)

from collections import defaultdict
from typing import Annotated, List, Optional, Union

from databases import Database
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request, HTTPException, Header
from fastapi.openapi.utils import get_openapi
from google.auth.transport import requests
from google.oauth2 import id_token
import orjson
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import JSONResponse, Response, HTMLResponse, PlainTextResponse

from api_types import (
    PlainSuccess,
    ContentListSuccess,
    ContentSuccess,
    ContentIdSuccess,
    UserSuccess,
    UserListSuccess,
    TagListSuccess,
    ContentUpload,
    IsAuthResponse,
    BanEntry,
    Error,
)
from modules.mca.invalid_report import InvalidReport
from modules.mca.valid import ValidModule
from modules.module import Module
from utils import (
    login_user,
    token_to_userid,
    owns_content,
    get_content_class,
    has_liked,
    has_tag,
    get_user_class,
    get_tags,
    get_project_tags,
    is_moderator,
    set_moderator,
    set_banned,
    user_exists,
    exists,
    BASE_SELECT,
    BASE_LITE_SELECT,
    get_lite_user_class,
    get_lite_content_class,
    has_reported,
    refresh_precomputation,
    set_dirty,
)

load_dotenv()

description = """
A simple and generic user asset library.
"""

tags_metadata = [
    {
        "name": "Auth",
        "description": "Authentication happens via Google Sign-In, the verified userid serves as unique identifier to a users account. On authentication, the user supplies it's access token, which it then uses for all API calls requiring authentication.",
    },
    {
        "name": "Content",
        "description": "A content is assigned to a project, contains a json metadata and a raw blob data field.",
    },
    {
        "name": "Likes",
        "description": "A content can be liked, raising the accumulated like counter on the content as well as providing a way to list a users liked content. Can also be used for a content subscription model.",
    },
    {
        "name": "Tags",
        "description": "The owner or moderator can add and remove tags used to filter content.",
    },
    {
        "name": "Users",
        "description": "A user is a unique, authenticated account with a non unique, changeable username. A user is required to interact with most API calls.",
    },
    {
        "name": "Admin",
        "description": "Administrative tools",
    },
]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await database.connect()
    await setup()

    instrumentator.expose(_app)

    yield

    await database.disconnect()


app = FastAPI(lifespan=lifespan)

# noinspection PyTypeChecker
app.add_middleware(GZipMiddleware, minimum_size=4096, compresslevel=6)

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")


# Custom OpenAPI to fix missing description
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="Immersive Library",
        version="0.0.1",
        description=description,
        routes=app.routes,
    )

    openapi_schema["tags"] = tags_metadata

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# Open Database
database = Database("sqlite:///database.db")

# Prometheus integration
instrumentator = Instrumentator().instrument(app)


@app.exception_handler(HTTPException)
async def validation_exception_handler(request: Request, exc: HTTPException):
    assert request
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail},
    )


# Create tables
async def setup():
    # Content
    await database.execute(
        "CREATE TABLE IF NOT EXISTS users (oid INTEGER PRIMARY KEY AUTOINCREMENT, google_userid CHAR, token CHAR, username CHAR, moderator INTEGER, banned INTEGER)"
    )
    await database.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS users_google_userid on users (google_userid)"
    )
    await database.execute("CREATE INDEX IF NOT EXISTS users_token on users (token)")

    # Content
    await database.execute(
        "CREATE TABLE IF NOT EXISTS content (oid INTEGER PRIMARY KEY AUTOINCREMENT, userid CHAR, project CHAR, title CHAR, version int DEFAULT 0, meta TEXT, data BLOB)"
    )
    await database.execute("DROP INDEX IF EXISTS content_project")

    # Reports
    await database.execute(
        "CREATE TABLE IF NOT EXISTS reports (userid CHAR, contentid INTEGER, reason CHAR)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS reports_userid on reports (userid)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS reports_contentid on reports (contentid)"
    )
    await database.execute("DROP INDEX IF EXISTS reports_reason")

    # Likes
    await database.execute(
        "CREATE TABLE IF NOT EXISTS likes (userid CHAR, contentid INTEGER)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS likes_contentid on likes (contentid)"
    )

    # Tags
    await database.execute(
        "CREATE TABLE IF NOT EXISTS tags (contentid INTEGER, tag CHAR)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS tags_contentid on tags (contentid)"
    )

    # Precomputation
    await database.execute(
        "CREATE TABLE IF NOT EXISTS precomputation (contentid INTEGER PRIMARY KEY, dirty INTEGER, tags CHAR, likes INTEGER, reports INTEGER, counter_reports INTEGER)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS precomputation_contentid on precomputation (contentid)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS precomputation_dirty on precomputation (dirty)"
    )

    await refresh_precomputation(database)


# Modules allow for project specific post-processing
modules: defaultdict[str, List[Module]] = defaultdict(lambda: [])

modules["mca"].append(ValidModule(database))
modules["mca"].append(InvalidReport(database))

T = TypeVar("T", bound=BaseModel)


def encode(r: T) -> T:
    # noinspection PyTypeChecker
    return Response(orjson.dumps(r, default=vars), media_type="application/json")  # pyright: ignore [reportReturnType]


def decode(r: Union[BaseModel, Response]) -> dict:
    if isinstance(r, Response):
        return orjson.loads(r.body)
    else:
        return r.model_dump()


@app.get("/", response_class=HTMLResponse)
async def get_front(request: Request):
    return templates.TemplateResponse(
        "statistics.html",
        {"request": request, "statistics_data": await get_statistics()},
    )


@app.post(
    "/v1/auth",
    responses={401: {"model": Error}, 400: {"model": Error}},
    tags=["Auth"],
    summary="Authenticate user",
)
async def auth(
    credential: Annotated[str, Form()],
    state: Annotated[Optional[str], Form()] = None,
    username: Optional[str] = None,
    token: Optional[str] = None,
) -> JSONResponse:
    if state is not None:
        state_dict = orjson.loads(state)
        token = base64.b64decode(state_dict.get("token")).decode("utf-8")
        username = base64.b64decode(state_dict.get("username")).decode("utf-8")

    if token is None or username is None:
        raise HTTPException(400, "Token or username missing")

    if len(token) < 16:
        raise HTTPException(400, "Token should at very least contain 16 bytes")

    try:
        info = id_token.verify_oauth2_token(
            credential, requests.Request(), os.getenv("CLIENT_ID")
        )

        userid = info["sub"]

        # Update session for user
        await login_user(database, userid, username, token)

        return JSONResponse(
            status_code=200,
            content="Authentication successful! You may now close the browser.",
        )
    except ValueError:
        raise HTTPException(401, "Validation failed")


@app.get(
    "/v1/auth",
    tags=["Auth"],
    summary="Check if user is authenticated",
)
async def is_auth(
    token: Optional[str] = None, authorization: str = Header(None)
) -> IsAuthResponse:
    executor_userid = await token_to_userid(database, token, authorization)

    if executor_userid is None:
        return encode(IsAuthResponse(authenticated=False))
    else:
        return encode(IsAuthResponse(authenticated=True))


@app.get("/v1/stats")
async def get_statistics():
    content_count = await database.fetch_one("SELECT count(*) from content")
    content_count_liked = await database.fetch_one(
        """
        SELECT count(*)
        FROM content
        INNER JOIN precomputation ON content.oid = precomputation.contentid
        WHERE precomputation.likes > 10
    """
    )
    users_count = await database.fetch_one("SELECT count(*) FROM users")
    likes_count = await database.fetch_one("SELECT count(*) FROM likes")
    reports_count = await database.fetch_one("SELECT count(*) FROM reports")

    top_tags = await database.fetch_all("""
        SELECT tag
        FROM tags
        GROUP BY tag
        HAVING count(*) > 10
        ORDER BY count(*) desc
        LIMIT 33
    """)

    random_oid = await database.fetch_one(
        """
        SELECT oid
        FROM (
            SELECT content.oid
            FROM content
            INNER JOIN precomputation ON content.oid = precomputation.contentid
            WHERE precomputation.likes > 100
            ORDER BY RANDOM()
            LIMIT 1
        );
    """
    )

    if (
        content_count is None
        or content_count_liked is None
        or users_count is None
        or likes_count is None
        or reports_count is None
        or top_tags is None
        or random_oid is None
    ):
        return {
            "oid": 0,
            "top_tags": "None",
            "content": "0",
            "content_liked": "0",
            "users": "0",
            "likes": "0",
            "reports": "0",
        }

    return {
        "oid": random_oid[0],
        "top_tags": ", ".join([t[0] for t in top_tags[3:]]),
        "content": "{:,}".format(content_count[0]),
        "content_liked": "{:,}".format(content_count_liked[0]),
        "users": "{:,}".format(users_count[0]),
        "likes": "{:,}".format(likes_count[0]),
        "reports": "{:,}".format(reports_count[0]),
    }


@app.get("/v1/content/{project}", tags=["Content"])
async def list_content(
    project: str, tag_filter: Optional[str] = None, invert_filter: bool = False
) -> ContentListSuccess:
    return await list_content_v2(
        project,
        whitelist=None if invert_filter else tag_filter,
        blacklist=tag_filter if invert_filter else None,
        limit=1000,
    )


@app.get("/v2/content/{project}", tags=["Content"])
async def list_content_v2(
    project: str,
    whitelist: Optional[str] = None,
    blacklist: Optional[str] = None,
    filter_banned: bool = True,
    filter_reported: bool = True,
    moderator: bool = False,
    offset: int = 0,
    limit: int = 10,
    order: str = "oid",
    descending: bool = False,
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> ContentListSuccess:
    prompt = BASE_LITE_SELECT
    values: dict[str, Union[str, int]] = {"project": project}

    prompt += "\n WHERE c.project = :project"

    # Hide personal banned content
    if token is not None and not moderator:
        userid = await token_to_userid(database, token, authorization)

        if userid is not None:
            prompt += """
             AND NOT EXISTS (SELECT *
                        FROM reports
                        WHERE reports.contentid = c.oid AND reports.reason = 'DEFAULT' AND reports.userid = :userid)
            """
            values["userid"] = userid

    # Only show reported content
    if moderator:
        prompt += "\n AND (1 + likes / 10.0 - reports + counter_reports * 10.0 < 0.0 OR users.banned)"
    else:
        # Remove content from banned users
        if filter_banned:
            prompt += "\n AND NOT users.banned"

        # Remove reported content
        if filter_reported:
            prompt += (
                "\n AND 1 + likes / 10.0 - reports + counter_reports * 10.0 >= 0.0"
            )

    # Only if all terms matches either a tag or the title, allow this content
    if whitelist:
        for index, term in enumerate(
            list(v.strip() for v in whitelist.split(",") if v.strip)
        ):
            prompt += f"\n AND (username LIKE :whitelist_term_{index} OR title LIKE :whitelist_term_{index} OR EXISTS(SELECT * FROM tags WHERE tags.contentid == c.oid AND tags.tag LIKE :whitelist_term_{index}))"
            values[f"whitelist_term_{index}"] = f"%{term}%"

    # Only if no term matches a tag
    if blacklist:
        for index, term in enumerate(
            list(v.strip() for v in blacklist.split(",") if v.strip)
        ):
            prompt += f"\n AND NOT EXISTS(SELECT * FROM tags WHERE tags.contentid == c.oid AND tags.tag LIKE :blacklist_term_{index})"
            values[f"blacklist_term_{index}"] = f"%{term}%"

    # Order by
    if order in {"date", "likes", "title", "reports"}:
        if order == "date":
            order = "c.oid"
        prompt += f"\n ORDER BY {order} " + ("DESC" if descending else "ASC")

    # Limit
    prompt += "\n LIMIT :limit OFFSET :offset"
    values["limit"] = limit
    values["offset"] = offset

    # Fetch
    content = await database.fetch_all(prompt, values)

    # Convert to content accessors, which are more lightweight than the actual content instances
    contents = [get_lite_content_class(c) for c in content]

    return encode(ContentListSuccess(contents=contents))


@app.get("/v1/content/{project}/{contentid}", tags=["Content"])
async def get_content(project: str, contentid: int) -> ContentSuccess:
    assert project
    content = await database.fetch_one(
        BASE_SELECT + "WHERE c.oid = :contentid", {"contentid": contentid}
    )

    if content is None:
        raise HTTPException(404, "Content not found")

    # noinspection PyArgumentList
    return encode(ContentSuccess(content=get_content_class(content)))


@app.post(
    "/v1/content/{project}",
    responses={401: {"model": Error}, 428: {"model": Error}, 400: {"model": Error}},
    tags=["Content"],
)
async def add_content(
    project: str,
    content: ContentUpload,
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> ContentIdSuccess:
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    # Check for duplicates
    if await exists(
        database,
        "SELECT count(*) FROM content WHERE project=:project AND data=:data",
        {"project": project, "data": content.payload},
    ):
        raise HTTPException(428, "Duplicate found!")

    # Call modules for content verification
    for module in modules[project]:
        exception = await module.pre_upload(content)
        if exception is not None:
            raise HTTPException(400, exception)

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

    # Call modules for eventual post-processing
    for module in modules[project]:
        await module.post_upload(contentid)

    await set_dirty(database, -1)

    return encode(ContentIdSuccess(contentid=contentid))


@app.put(
    "/v1/content/{project}/{contentid}",
    responses={401: {"model": Error}},
    tags=["Content"],
)
async def update_content(
    project: str,
    contentid: int,
    content: ContentUpload,
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> PlainSuccess:
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if not await owns_content(database, contentid, userid) and not await is_moderator(
        database, userid
    ):
        raise HTTPException(401, "Not your content")

    # Call modules for content verification
    for module in modules[project]:
        exception = await module.pre_upload(content)
        if exception is not None:
            raise HTTPException(400, str(exception))

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

    # Call modules for eventual post-processing
    for module in modules[project]:
        await module.post_upload(contentid)

    await set_dirty(database, contentid)

    return PlainSuccess()


# noinspection PyUnusedLocal
@app.delete(
    "/v1/content/{project}/{contentid}",
    responses={401: {"model": Error}},
    tags=["Content"],
)
async def delete_content(
    project: str,
    contentid: int,
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> PlainSuccess:
    assert project
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if not await owns_content(database, contentid, userid) and not await is_moderator(
        database, userid
    ):
        raise HTTPException(401, "Not your content")

    await database.execute(
        "DELETE FROM content WHERE oid=:contentid",
        {"contentid": contentid},
    )

    return PlainSuccess()


# noinspection PyUnusedLocal
@app.post(
    "/v1/like/{project}/{contentid}",
    responses={401: {"model": Error}, 428: {"model": Error}},
    tags=["Likes"],
)
async def add_like(
    project: str,
    contentid: int,
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> PlainSuccess:
    assert project
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if await has_liked(database, userid, contentid):
        raise HTTPException(428, "Already liked")

    await database.execute(
        "INSERT INTO likes (userid, contentid) VALUES(:userid, :contentid)",
        {"userid": userid, "contentid": contentid},
    )

    await set_dirty(database, contentid)

    return PlainSuccess()


# noinspection PyUnusedLocal
@app.delete(
    "/v1/like/{project}/{contentid}",
    responses={401: {"model": Error}, 428: {"model": Error}},
    tags=["Likes"],
)
async def delete_like(
    project: str,
    contentid: int,
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> PlainSuccess:
    assert project
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if not await has_liked(database, userid, contentid):
        raise HTTPException(428, "Not liked previously")

    await database.execute(
        "DELETE FROM likes WHERE userid=:userid AND contentid=:contentid",
        {"userid": userid, "contentid": contentid},
    )

    await set_dirty(database, contentid)

    return PlainSuccess()


# noinspection PyUnusedLocal
@app.post(
    "/v1/report/{project}/{contentid}/{reason}",
    responses={401: {"model": Error}, 428: {"model": Error}},
    tags=["Likes"],
)
async def add_report(
    project: str,
    contentid: int,
    reason: str,
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> PlainSuccess:
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if await has_reported(database, userid, contentid, reason):
        raise HTTPException(428, "Already reported")

    await database.execute(
        "INSERT INTO reports (userid, contentid, reason) VALUES(:userid, :contentid, :reason)",
        {"userid": userid, "contentid": contentid, "reason": reason},
    )

    # Call modules for eventual post-processing
    for module in modules[project]:
        await module.post_report(contentid, reason)

    await set_dirty(database, contentid)

    return PlainSuccess()


# noinspection PyUnusedLocal
@app.delete(
    "/v1/report/{project}/{contentid}/{reason}",
    responses={401: {"model": Error}, 428: {"model": Error}},
    tags=["Likes"],
)
async def delete_report(
    project: str,
    contentid: int,
    reason: str,
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> PlainSuccess:
    assert project
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if not await has_reported(database, userid, contentid, reason):
        raise HTTPException(428, "Not liked previously")

    await database.execute(
        "DELETE FROM reports WHERE userid=:userid AND contentid=:contentid AND reason=:reason",
        {"userid": userid, "contentid": contentid, "reason": reason},
    )

    await set_dirty(database, contentid)

    return PlainSuccess()


@app.get("/v1/tag/{project}", tags=["Tags"])
async def list_project_tags(project: str) -> TagListSuccess:
    tags = await get_project_tags(database, project)
    return encode(TagListSuccess(tags=tags))


# noinspection PyUnusedLocal
@app.get("/v1/tag/{project}/{contentid}", tags=["Tags"])
async def list_content_tags(project: str, contentid: int) -> TagListSuccess:
    assert project
    tags = await get_tags(database, contentid)
    return encode(TagListSuccess(tags=tags))


# noinspection PyUnusedLocal
@app.post(
    "/v1/tag/{project}/{contentid}/{tag}",
    responses={401: {"model": Error}, 428: {"model": Error}},
    tags=["Tags"],
)
async def add_tag(
    project: str,
    contentid: int,
    tag: str,
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> PlainSuccess:
    assert project
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if not await owns_content(database, contentid, userid) and not await is_moderator(
        database, userid
    ):
        raise HTTPException(401, "Not your content")

    if "," in tag:
        raise HTTPException(401, "Contains invalid characters")

    if await has_tag(database, contentid, tag):
        raise HTTPException(428, "Already tagged")

    await database.execute(
        "INSERT INTO tags (contentid, tag) VALUES(:contentid, :tag)",
        {"contentid": contentid, "tag": tag},
    )

    await set_dirty(database, contentid)

    return PlainSuccess()


# noinspection PyUnusedLocal
@app.delete(
    "/v1/tag/{project}/{contentid}/{tag}",
    responses={401: {"model": Error}, 428: {"model": Error}},
    tags=["Tags"],
)
async def delete_tag(
    project: str,
    contentid: int,
    tag: str,
    token: Optional[str] = None,
    authorization: str = Header(None),
) -> PlainSuccess:
    assert project
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if not await owns_content(database, contentid, userid) and not await is_moderator(
        database, userid
    ):
        raise HTTPException(401, "Not your content")

    if not await has_tag(database, contentid, tag):
        raise HTTPException(428, "Not tagged")

    await database.execute(
        "DELETE FROM tags WHERE contentid=:contentid AND tag=:tag",
        {"contentid": contentid, "tag": tag},
    )

    await set_dirty(database, contentid)

    return PlainSuccess()


@app.get(
    "/v1/bans",
    tags=["Users"],
)
async def get_banned() -> List[BanEntry]:
    content = await database.fetch_all(
        """
        SELECT oid, username
        FROM users
        WHERE banned == 1
    """
    )

    return [BanEntry(userid=u[0], username=u[1]) for u in content]


@app.get(
    "/v1/user/{project}/",
    tags=["Users"],
)
async def get_users(project: str) -> UserListSuccess:
    content = await database.fetch_all(
        """
    SELECT oid,
       username,
       moderator,
       CASE
           WHEN submitted_content.submission_count is NULL THEN 0
           ELSE submitted_content.submission_count END                             as submission_count,
       CASE WHEN likes_given.count is NULL THEN 0 ELSE likes_given.count END       as likes_given,
       CASE WHEN likes_received.count is NULL THEN 0 ELSE likes_received.count END as likes_received
    FROM users

         LEFT JOIN (SELECT content.userid, COUNT(content.oid) as submission_count
                    FROM content
                    WHERE content.project = :project
                    GROUP BY content.userid) submitted_content ON submitted_content.userid = users.oid

         LEFT JOIN (SELECT likes.userid, COUNT(likes.oid) as count
                    FROM likes
                    GROUP BY likes.userid) likes_given ON likes_given.userid = users.oid

         LEFT JOIN (SELECT c2.userid, COUNT(likes.oid) as count
                    FROM likes
                             INNER JOIN content c2 ON c2.oid = likes.contentid
                             WHERE c2.project = :project AND likes.userid != c2.userid
                    GROUP BY c2.userid) likes_received on likes_received.userid = users.oid
    """,
        {"project": project},
    )

    return encode(UserListSuccess(users=[get_lite_user_class(*c) for c in content]))


@app.get(
    "/v1/user/{project}/me",
    tags=["Users"],
    responses={401: {"model": Error}},
)
async def get_me(
    project: str, token: Optional[str] = None, authorization: str = Header(None)
) -> UserSuccess:
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    return await get_user(project, userid)


@app.get(
    "/v1/user/{project}/{userid}/",
    tags=["Users"],
    responses={404: {"model": Error}},
)
async def get_user(project: str, userid: int) -> UserSuccess:
    content = await database.fetch_one(
        "SELECT oid, username, moderator FROM users WHERE oid=:userid",
        {"userid": userid},
    )

    if content is None:
        raise HTTPException(404, "User doesn't exist")

    return encode(
        UserSuccess(
            user=await get_user_class(
                database,
                project,
                content["oid"],
                content["username"],
                content["moderator"],
            )
        )
    )


@app.put(
    "/v1/user/{userid}",
    tags=["Users"],
    responses={401: {"model": Error}, 403: {"model": Error}, 404: {"model": Error}},
)
async def set_user(
    userid: int,
    token: Optional[str] = None,
    authorization: str = Header(None),
    banned: Optional[bool] = None,
    moderator: Optional[bool] = None,
    purge=False,
) -> PlainSuccess:
    executor_userid = await token_to_userid(database, token, authorization)

    if executor_userid is None:
        raise HTTPException(401, "Token invalid")

    if not await is_moderator(database, executor_userid):
        raise HTTPException(403, "Not a moderator")

    if not await user_exists(database, userid):
        raise HTTPException(404, "User does not exist")

    # Change banned status
    if banned is not None:
        await set_banned(database, userid, banned)

    # Change moderator status
    if moderator is not None:
        await set_moderator(database, userid, moderator)

    # Delete the users content
    if purge is True:
        await database.execute(
            "DELETE FROM content WHERE userid=:userid", {"userid": userid}
        )
        await database.execute(
            "DELETE FROM likes WHERE userid=:userid", {"userid": userid}
        )

    return PlainSuccess()


# Administrative endpoints


@app.get(
    "/v1/tools/post-process/{project}",
    responses={401: {"model": Error}},
    tags=["Admin"],
)
async def run_post_upload_callbacks(
    project: str, token: Optional[str] = None, authorization: str = Header(None)
) -> PlainTextResponse:
    userid = await token_to_userid(database, token, authorization)

    if userid is None:
        raise HTTPException(401, "Token invalid")

    if not await is_moderator(database, userid):
        raise HTTPException(401, "Not an moderator")

    content = await database.fetch_all(
        "SELECT oid FROM content WHERE project=:project",
        {"project": project},
    )

    # Call modules for eventual post-processing
    processed = 0
    for c in content:
        processed += 1
        for module in modules[project]:
            await module.post_upload(*c)

    return PlainTextResponse(
        f"Processed {processed} entries.",
    )
