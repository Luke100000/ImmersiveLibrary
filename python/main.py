import os
import sqlite3
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Annotated, List

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Form
from fastapi.openapi.utils import get_openapi
from google.auth.transport import requests
from google.oauth2 import id_token
from orjson import orjson
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import JSONResponse, Response

from api_types import (
    PlainSuccess,
    Error,
    ContentListSuccess,
    ContentSuccess,
    ContentIdSuccess,
    UserSuccess,
    UserListSuccess,
    TagListSuccess,
    ContentUpload,
    IsAuthResponse,
)
from modules.mca.valid import ValidModule
from modules.module import Module
from utils import (
    login_user,
    token_to_userid,
    owns_content,
    get_error,
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
    get_lite_content_class,
    BASE_SELECT,
    BASE_LITE_SELECT,
    get_lite_user_class,
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

app = FastAPI()

app.add_middleware(GZipMiddleware)


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
con = sqlite3.connect("database.db", check_same_thread=False)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    con.close()


# Prometheus integration
instrumentator = Instrumentator().instrument(app)


@app.on_event("startup")
async def _startup():
    instrumentator.expose(app)


# Create tables
def setup():
    cur = con.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS users (oid INTEGER PRIMARY KEY AUTOINCREMENT, google_userid CHAR, token CHAR, username CHAR, moderator INTEGER, banned INTEGER)"
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS users_google_userid on users (google_userid)"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS users_token on users (token)")

    cur.execute(
        "CREATE TABLE IF NOT EXISTS content (oid INTEGER PRIMARY KEY AUTOINCREMENT, userid CHAR, project CHAR, title CHAR, version int DEFAULT 0, meta TEXT, data BLOB)"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS content_project on content (project)")

    cur.execute("CREATE TABLE IF NOT EXISTS likes (userid CHAR, contentid INTEGER)")
    cur.execute("CREATE INDEX IF NOT EXISTS likes_contentid on likes (contentid)")

    cur.execute("CREATE TABLE IF NOT EXISTS tags (contentid INTEGER, tag CHAR)")
    cur.execute("CREATE INDEX IF NOT EXISTS tags_contentid on tags (contentid)")

    cur.close()
    con.commit()


setup()

# Modules allow for project specific post-processing
modules: defaultdict[str, List[Module]] = defaultdict(lambda: [])

modules["mca"].append(ValidModule(con))


def encode(r: Response):
    return Response(orjson.dumps(r, default=vars), media_type="application/json")


@app.post(
    "/v1/auth",
    responses={401: {"model": Error}, 400: {"model": Error}},
    tags=["Auth"],
    summary="Authenticate user",
)
def auth(credential: Annotated[str, Form()], username: str, token: str) -> dict:
    if len(token) < 16:
        return get_error(400, "Token should at very least contain 16 bytes")

    try:
        info = id_token.verify_oauth2_token(
            credential, requests.Request(), os.getenv("CLIENT_ID")
        )

        userid = info["sub"]

        # Update session for user
        login_user(con, userid, username, token)

        return JSONResponse(
            status_code=200,
            content="Authentication successful! You may now close the browser.",
        )
    except ValueError:
        return get_error(401, "Validation failed")


@app.get(
    "/v1/auth",
    tags=["Auth"],
    summary="Check if user is authenticated",
)
def is_auth(token: str) -> dict:
    executor_userid = token_to_userid(con, token)

    if executor_userid is None:
        return encode(IsAuthResponse(authenticated=False))
    else:
        return encode(IsAuthResponse(authenticated=True))


@app.get("/v1/content/{project}", tags=["Content"])
def list_content(
    project: str, tag_filter: str = None, invert_filter: bool = False
) -> ContentListSuccess:
    if tag_filter is None:
        content = con.execute(
            BASE_LITE_SELECT + "WHERE c.project = ?",
            (project,),
        ).fetchall()
    else:
        content = con.execute(
            BASE_LITE_SELECT
            + f"WHERE c.project = ? AND {'NOT' if invert_filter else ''} EXISTS(SELECT * FROM tags WHERE tags.contentid == c.oid AND tags.tag IS ?)",
            (project, tag_filter),
        ).fetchall()

    return encode(
        ContentListSuccess(contents=[get_lite_content_class(*c) for c in content])
    )


# noinspection PyUnusedLocal
@app.get("/v1/content/{project}/{contentid}", tags=["Content"])
def get_content(project: str, contentid: int) -> ContentSuccess:
    content = con.execute(
        BASE_SELECT + "WHERE c.oid = ?",
        (contentid,),
    ).fetchone()

    return encode(ContentSuccess(content=get_content_class(*content)))


@app.post(
    "/v1/content/{project}",
    responses={401: {"model": Error}, 428: {"model": Error}, 400: {"model": Error}},
    tags=["Content"],
)
def add_content(project: str, content: ContentUpload, token: str) -> ContentIdSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Token invalid")

    # Check for duplicates
    if exists(
        con,
        "SELECT count(*) FROM content WHERE project=? AND data=?",
        (project, content.payload),
    ):
        return get_error(428, "Duplicate found!")

    # Call modules for content verification
    for module in modules[project]:
        exception = module.pre_upload(content)
        if exception is not None:
            return get_error(400, exception)

    content = con.execute(
        "INSERT INTO content (userid, project, title, meta, data) VALUES(?, ?, ?, ?, ?)",
        (userid, project, content.title, content.meta, content.payload),
    )
    con.commit()

    # Call modules for eventual post-processing
    for module in modules[project]:
        module.post_upload(content.lastrowid)

    return encode(ContentIdSuccess(contentid=content.lastrowid))


@app.put(
    "/v1/content/{project}/{contentid}",
    responses={401: {"model": Error}},
    tags=["Content"],
)
def update_content(
    project: str, contentid: int, content: ContentUpload, token: str
) -> PlainSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Token invalid")

    if not owns_content(con, contentid, userid) and not is_moderator(con, userid):
        return get_error(401, "Not your content")

    # Call modules for content verification
    for module in modules[project]:
        exception = module.pre_upload(content)
        if exception is not None:
            return get_error(400, exception)

    con.execute(
        "UPDATE content SET title=?, meta=?, data=?, version=version+1 WHERE project=? AND oid=?",
        (
            content.title,
            content.meta,
            content.payload,
            project,
            contentid,
        ),
    )
    con.commit()

    # Call modules for eventual post-processing
    for module in modules[project]:
        module.post_upload(contentid)

    return PlainSuccess()


# noinspection PyUnusedLocal
@app.delete(
    "/v1/content/{project}/{contentid}",
    responses={401: {"model": Error}},
    tags=["Content"],
)
def delete_content(project: str, contentid: int, token: str) -> PlainSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Token invalid")

    if not owns_content(con, contentid, userid) and not is_moderator(con, userid):
        return get_error(401, "Not your content")

    con.execute(
        "DELETE FROM content WHERE oid=?",
        (contentid,),
    )
    con.commit()

    return PlainSuccess()


# noinspection PyUnusedLocal
@app.post(
    "/v1/like/{project}/{contentid}",
    responses={401: {"model": Error}, 428: {"model": Error}},
    tags=["Likes"],
)
def add_like(project: str, contentid: int, token: str) -> PlainSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Token invalid")

    if has_liked(con, userid, contentid):
        return get_error(428, "Already liked")

    con.execute(
        "INSERT INTO likes (userid, contentid) VALUES(?, ?)",
        (userid, contentid),
    )
    con.commit()

    return PlainSuccess()


# noinspection PyUnusedLocal
@app.delete(
    "/v1/like/{project}/{contentid}",
    responses={401: {"model": Error}, 428: {"model": Error}},
    tags=["Likes"],
)
def delete_like(project: str, contentid: int, token: str) -> PlainSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Token invalid")

    if not has_liked(con, userid, contentid):
        return get_error(428, "Not liked previously")

    con.execute(
        "DELETE FROM likes WHERE userid=? AND contentid=?",
        (userid, contentid),
    )
    con.commit()

    return PlainSuccess()


@app.get("/v1/tag/{project}", tags=["Tags"])
def list_project_tags(project: str) -> TagListSuccess:
    cur = con.cursor()
    tags = get_project_tags(cur, project)
    cur.close()
    return encode(TagListSuccess(tags=tags))


# noinspection PyUnusedLocal
@app.get("/v1/tag/{project}/{contentid}", tags=["Tags"])
def list_content_tags(project: str, contentid: int) -> TagListSuccess:
    cur = con.cursor()
    tags = get_tags(cur, contentid)
    cur.close()
    return encode(TagListSuccess(tags=tags))


# noinspection PyUnusedLocal
@app.post(
    "/v1/tag/{project}/{contentid}/{tag}",
    responses={401: {"model": Error}, 428: {"model": Error}},
    tags=["Tags"],
)
def add_tag(project: str, contentid: int, tag: str, token: str) -> PlainSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Token invalid")

    if not owns_content(con, contentid, userid) and not is_moderator(con, userid):
        return get_error(401, "Not your content")

    if "," in tag:
        return get_error(401, "Contains invalid characters")

    if has_tag(con, contentid, tag):
        return get_error(428, "Already tagged")

    con.execute(
        "INSERT INTO tags (contentid, tag) VALUES(?, ?)",
        (contentid, tag),
    )
    con.commit()

    return PlainSuccess()


# noinspection PyUnusedLocal
@app.delete(
    "/v1/tag/{project}/{contentid}/{tag}",
    responses={401: {"model": Error}, 428: {"model": Error}},
    tags=["Tags"],
)
def delete_tag(project: str, contentid: int, tag: str, token: str) -> PlainSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Token invalid")

    if not owns_content(con, contentid, userid) and not is_moderator(con, userid):
        return get_error(401, "Not your content")

    if not has_tag(con, contentid, tag):
        return get_error(428, "Not tagged")

    con.execute(
        "DELETE FROM tags WHERE contentid=? AND tag=?",
        (contentid, tag),
    )
    con.commit()

    return PlainSuccess()


@app.get(
    "/v1/user/{project}/",
    tags=["Users"],
)
def get_users(project: str) -> UserListSuccess:
    content = con.execute(
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
                    WHERE content.project = ?
                    GROUP BY content.userid) submitted_content ON submitted_content.userid = oid

         LEFT JOIN (SELECT likes.userid, COUNT(likes.oid) as count
                    FROM likes
                    GROUP BY likes.userid) likes_given ON likes_given.userid = oid

         LEFT JOIN (SELECT likes.userid, COUNT(likes.oid) as count
                    FROM likes
                             INNER JOIN content c2 ON c2.userid = likes.userid AND c2.oid = likes.contentid
                             WHERE c2.project = ?
                    GROUP BY likes.userid) likes_received on likes_received.userid = oid
    """,
        (project, project),
    ).fetchall()

    return encode(UserListSuccess(users=[get_lite_user_class(*c) for c in content]))


@app.get(
    "/v1/user/{project}/me",
    tags=["Users"],
    responses={401: {"model": Error}},
)
def get_me(project: str, token: str) -> UserSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Token invalid")

    return get_user(project, userid)


@app.get(
    "/v1/user/{project}/{userid}/",
    tags=["Users"],
    responses={404: {"model": Error}},
)
def get_user(project: str, userid: int) -> UserSuccess:
    content = con.execute(
        "SELECT oid, username, moderator FROM users WHERE oid=?",
        (userid,),
    ).fetchone()

    if content is None:
        return get_error(404, "User doesn't exist")

    return encode(UserSuccess(user=get_user_class(con, project, *content)))


@app.put(
    "/v1/user/{userid}/",
    tags=["Users"],
    responses={401: {"model": Error}, 403: {"model": Error}, 404: {"model": Error}},
)
def set_user(
    userid: int, token: str, banned: bool = None, moderator: bool = None, purge=False
) -> PlainSuccess:
    executor_userid = token_to_userid(con, token)

    if executor_userid is None:
        return get_error(401, "Token invalid")

    if not is_moderator(con, executor_userid):
        return get_error(403, "Not a moderator")

    if not user_exists(con, userid):
        return get_error(404, "User does not exist")

    # Change banned status
    if banned is not None:
        set_banned(con, userid, banned)

    # Change moderator status
    if moderator is not None:
        set_moderator(con, userid, moderator)

    # Delete the users content
    if purge is True:
        con.execute("DELETE FROM content WHERE userid=?", (userid,))
        con.execute("DELETE FROM likes WHERE userid=?", (userid,))

    return PlainSuccess()


# Administrative endpoints


@app.get(
    "/v1/tools/post-process/{project}",
    responses={401: {"model": Error}},
    tags=["Admin"],
)
def run_post_upload_callbacks(project: str, token: str) -> PlainSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Token invalid")

    if not is_moderator(con, userid):
        return get_error(401, "Not an moderator")

    content = con.execute(
        "SELECT oid FROM content WHERE project=?",
        (project,),
    )
    con.commit()

    # Call modules for eventual post-processing
    processed = 0
    for c in content:
        processed += 1
        for module in modules[project]:
            module.post_upload(*c)

    return JSONResponse(
        status_code=200,
        content=f"Processed {processed} entries.",
    )
