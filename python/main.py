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

from api_types import (
    Oid,
    PlainSuccess,
    Error,
    ContentListSuccess,
    ContentSuccess,
    OidSuccess,
    UserSuccess,
    UserListSuccess,
    TagListSuccess,
)
from utils import (
    login_user,
    token_to_userid,
    own,
    get_error,
    get_content_class,
    has_liked,
    has_tag,
    get_user_class,
    get_tags,
    get_project_tags,
)

load_dotenv()

description = """
A simple and generic user asset library.
"""

tags_metadata = [
    {
        "name": "Auth",
        "description": "",
    },
    {
        "name": "Content",
        "description": "",
    },
    {
        "name": "Likes",
        "description": "",
    },
    {
        "name": "Tags",
        "description": "",
    },
    {
        "name": "Users",
        "description": "",
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
        "CREATE TABLE IF NOT EXISTS users (google_userid CHAR, token CHAR, username CHAR, moderator INTEGER)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS users_google_userid on users (google_userid)"
    )

    cur.execute(
        "CREATE TABLE IF NOT EXISTS content (userid CHAR, project CHAR, title CHAR, meta TEXT, data BLOB)"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS content_project on content (project)")

    cur.execute("CREATE TABLE IF NOT EXISTS likes (userid CHAR, id INTEGER)")
    cur.execute("CREATE INDEX IF NOT EXISTS likes_id on likes (id)")

    cur.execute("CREATE TABLE IF NOT EXISTS tags (id INTEGER, tag CHAR)")
    cur.execute("CREATE INDEX IF NOT EXISTS tags_id on tags (id)")

    cur.close()
    con.commit()


setup()


@app.post(
    "/auth",
    responses={401: {"model": Error}},
    tags=["Auth"],
    summary="Authenticate user",
)
def auth(credential: Annotated[str, Form()], username: str, token: str) -> dict:
    try:
        info = id_token.verify_oauth2_token(
            credential, requests.Request(), os.getenv("CLIENT_ID")
        )

        userid = info["sub"]

        # Update session for user
        login_user(con, userid, username, token)

        return PlainSuccess()
    except ValueError:
        return get_error(401, "Validation failed")


@app.get("/content/{project}", tags=["Content"])
def list_content(project: str) -> ContentListSuccess:
    cur = con.cursor()
    content = cur.execute(
        "SELECT oid, userid, title FROM content WHERE project=?",
        (project,),
    ).fetchall()

    r = ContentListSuccess(data=[get_content_class(cur, *c) for c in content])

    cur.close()
    return r


# noinspection PyUnusedLocal
@app.get("/content/{project}/{oid}", tags=["Content"])
def get_content(project: str, oid: int) -> ContentSuccess:
    content = con.execute(
        "SELECT oid, userid, title, meta, data FROM content WHERE oid=?",
        (oid,),
    ).fetchone()

    cur = con.cursor()
    r = ContentSuccess(data=get_content_class(cur, *content))
    cur.close()
    return r


@app.post("/content/{project}", responses={401: {"model": Error}}, tags=["Content"])
def add_content(
    project: str, title: str, meta: str, data: bytes, token: str
) -> OidSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Token invalid")

    content = con.execute(
        "INSERT INTO content (userid, project, title, meta, data) VALUES(?, ?, ?, ?, ?)",
        (userid, project, title, meta, data),
    )
    con.commit()

    return OidSuccess(data=Oid(oid=content.lastrowid))


@app.put(
    "/content/{project}/{oid}", responses={401: {"model": Error}}, tags=["Content"]
)
def update_content(
    project: str, oid: int, title: str, meta: str, data: bytes, token: str
) -> PlainSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Token invalid")

    con.execute(
        "UPDATE content SET title=?, meta=?, data=? WHERE userid=? AND project=? AND oid=?",
        (title, meta, data, userid, project, oid),
    )
    con.commit()

    return PlainSuccess()


@app.delete(
    "/content/{project}/{oid}", responses={401: {"model": Error}}, tags=["Content"]
)
def delete_content(project: str, oid: int, token: str) -> PlainSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Token invalid")

    if not own(con, oid, userid):
        return get_error(401, "Not your item")

    con.execute(
        "DELETE FROM content WHERE userid=? AND project=? AND oid=?",
        (userid, project, oid),
    )
    con.commit()

    return PlainSuccess()


# noinspection PyUnusedLocal
@app.put(
    "/like/{project}/{oid}",
    responses={401: {"model": Error}, 428: {"model": Error}},
    tags=["Likes"],
)
def add_like(project: str, oid: int, token: str) -> PlainSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Token invalid")

    if has_liked(con, oid, userid):
        return get_error(428, "Already liked")

    con.execute(
        "INSERT INTO likes (userid, id) VALUES(?, ?)",
        (userid, oid),
    )
    con.commit()

    return PlainSuccess()


# noinspection PyUnusedLocal
@app.delete(
    "/like/{project}/{oid}",
    responses={401: {"model": Error}, 428: {"model": Error}},
    tags=["Likes"],
)
def delete_like(project: str, oid: int, token: str) -> PlainSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Token invalid")

    if not has_liked(con, oid, userid):
        return get_error(428, "Not liked previously")

    con.execute(
        "DELETE FROM likes WHERE userid=? AND id=?",
        (userid, oid),
    )
    con.commit()

    return PlainSuccess()


@app.get("/tag/{project}", tags=["Tags"])
def list_project_tags(project: str) -> PlainSuccess:
    cur = con.cursor()
    tags = get_project_tags(cur, project)
    cur.close()
    return TagListSuccess(data=tags)


@app.get("/tag/{project}/{oid}", tags=["Tags"])
def list_item_tags(project: str, oid: int) -> TagListSuccess:
    cur = con.cursor()
    tags = get_tags(cur, oid)
    cur.close()
    return TagListSuccess(data=tags)


@app.put(
    "/tag/{project}/{oid}/{tag}",
    responses={401: {"model": Error}, 428: {"model": Error}},
    tags=["Tags"],
)
def add_tag(project: str, oid: int, tag: str, token: str) -> PlainSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Token invalid")

    if not own(con, oid, userid):
        return get_error(401, "Not your item")

    if has_tag(con, oid, tag):
        return get_error(428, "Already tagged")

    con.execute(
        "INSERT INTO tags (id, tag) VALUES(?, ?)",
        (oid, tag),
    )
    con.commit()

    return PlainSuccess()


@app.delete(
    "/tag/{project}/{oid}/{tag}",
    responses={401: {"model": Error}, 428: {"model": Error}},
    tags=["Tags"],
)
def delete_tag(project: str, oid: int, tag: str, token: str) -> PlainSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Token invalid")

    if not own(con, oid, userid):
        return get_error(401, "Not your item")

    if not has_tag(con, oid, tag):
        return get_error(428, "Not tagged")

    con.execute(
        "DELETE FROM tags WHERE id=? AND tag=?",
        (oid, tag),
    )
    con.commit()

    return PlainSuccess()


@app.get(
    "/user/{project}/",
    tags=["Users"],
)
def get_users(project: str) -> PlainSuccess:
    content = con.execute("SELECT oid, username, moderator FROM users").fetchall()

    return UserListSuccess(data=[get_user_class(con, project, *c) for c in content])


@app.get(
    "/user/{project}/{userid}/",
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

    return UserSuccess(data=get_user_class(con, project, *content))
