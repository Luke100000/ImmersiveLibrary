import os
import sqlite3
from contextlib import asynccontextmanager
from typing import Annotated

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Form
from fastapi.openapi.utils import get_openapi
from google.auth.transport import requests
from google.oauth2 import id_token
from starlette.responses import JSONResponse

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
)
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
]

app = FastAPI()


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

con = sqlite3.connect("database.db", check_same_thread=False)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    con.close()


def setup():
    cur = con.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS users (google_userid CHAR, token CHAR, username CHAR, moderator INTEGER, banned INTEGER)"
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS users_google_userid on users (google_userid)"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS users_token on users (token)")

    cur.execute(
        "CREATE TABLE IF NOT EXISTS content (userid CHAR, project CHAR, title CHAR, meta TEXT, data BLOB)"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS content_project on content (project)")

    cur.execute("CREATE TABLE IF NOT EXISTS likes (userid CHAR, contentid INTEGER)")
    cur.execute("CREATE INDEX IF NOT EXISTS likes_contentid on likes (contentid)")

    cur.execute("CREATE TABLE IF NOT EXISTS tags (contentid INTEGER, tag CHAR)")
    cur.execute("CREATE INDEX IF NOT EXISTS tags_contentid on tags (contentid)")

    cur.close()
    con.commit()


setup()


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


@app.get("/v1/content/{project}", tags=["Content"])
def list_content(project: str) -> ContentListSuccess:
    cur = con.cursor()
    content = cur.execute(
        "SELECT oid, userid, title FROM content WHERE project=?",
        (project,),
    ).fetchall()

    r = ContentListSuccess(contents=[get_content_class(cur, *c) for c in content])

    cur.close()
    return r


# noinspection PyUnusedLocal
@app.get("/v1/content/{project}/{contentid}", tags=["Content"])
def get_content(project: str, contentid: int) -> ContentSuccess:
    content = con.execute(
        "SELECT oid, userid, title, meta, data FROM content WHERE oid=?",
        (contentid,),
    ).fetchone()

    cur = con.cursor()
    r = ContentSuccess(content=get_content_class(cur, *content))
    cur.close()
    return r


@app.post("/v1/content/{project}", responses={401: {"model": Error}}, tags=["Content"])
def add_content(project: str, content: ContentUpload, token: str) -> ContentIdSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Token invalid")

    content = con.execute(
        "INSERT INTO content (userid, project, title, meta, data) VALUES(?, ?, ?, ?, ?)",
        (userid, project, content.title, content.meta, content.data),
    )
    con.commit()

    return ContentIdSuccess(contentid=content.lastrowid)


@app.put(
    "/content/{project}/{contentid}",
    responses={401: {"model": Error}},
    tags=["Content"],
)
def update_content(
    project: str, contentid: int, title: str, meta: str, data: bytes, token: str
) -> PlainSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Token invalid")

    con.execute(
        "UPDATE content SET title=?, meta=?, data=? WHERE userid=? AND project=? AND oid=?",
        (title, meta, data, userid, project, contentid),
    )
    con.commit()

    return PlainSuccess()


# noinspection PyUnusedLocal
@app.delete(
    "/content/{project}/{contentid}",
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
        "DELETE FROM content WHERE contentid=?",
        (contentid,),
    )
    con.commit()

    return PlainSuccess()


# noinspection PyUnusedLocal
@app.put(
    "/like/{project}/{contentid}",
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
    "/like/{project}/{contentid}",
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
def list_project_tags(project: str) -> PlainSuccess:
    cur = con.cursor()
    tags = get_project_tags(cur, project)
    cur.close()
    return TagListSuccess(tags=tags)


# noinspection PyUnusedLocal
@app.get("/v1/tag/{project}/{contentid}", tags=["Tags"])
def list_content_tags(project: str, contentid: int) -> TagListSuccess:
    cur = con.cursor()
    tags = get_tags(cur, contentid)
    cur.close()
    return TagListSuccess(tags=tags)


# noinspection PyUnusedLocal
@app.put(
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
def get_users(project: str) -> PlainSuccess:
    content = con.execute("SELECT oid, username, moderator FROM users").fetchall()

    return UserListSuccess(users=[get_user_class(con, project, *c) for c in content])


@app.get(
    "/v1/user/{project}/{userid}/",
    tags=["Users"],
    responses={404: {"model": Error}},
)
def get_user(project: str, userid: int) -> PlainSuccess:
    content = con.execute(
        "SELECT oid, username, moderator FROM users WHERE oid=?",
        (userid,),
    ).fetchone()

    if content is None:
        return get_error(404, "User doesnt exist")

    return UserSuccess(user=get_user_class(con, project, *content))


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
