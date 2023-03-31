import os
import sqlite3
from contextlib import asynccontextmanager
from typing import Annotated

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Form
from google.auth.transport import requests
from google.oauth2 import id_token

from api_types import (
    Oid,
    PlainSuccess,
    Error,
    ContentListSuccess,
    ContentSuccess,
    OidSuccess,
)
from utils import register_session, token_to_userid, own, get_error, get_content_class

load_dotenv()

app = FastAPI()

con = sqlite3.connect("database.db", check_same_thread=False)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    con.close()


def setup():
    cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS sessions (token CHAR, userid CHAR)")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS content (userid CHAR, project CHAR, title CHAR, meta TEXT, data BLOB)"
    )
    cur.execute("CREATE TABLE IF NOT EXISTS likes (userid CHAR, id INTEGER)")
    cur.close()
    con.commit()


setup()


@app.post("/auth", responses={401: {"model": Error}})
def auth(credential: Annotated[str, Form()], token: str):
    try:
        info = id_token.verify_oauth2_token(
            credential, requests.Request(), os.getenv("CLIENT_ID")
        )

        userid = info["sub"]

        # Update session for user
        register_session(con, userid, token)

        return {"success": True}
    except ValueError:
        return get_error(401, "Validation failed")


@app.get("/content/{project}")
def list_content(project: str) -> ContentListSuccess:
    content = con.execute(
        "SELECT oid, userid, title FROM content WHERE project=?",
        (project,),
    ).fetchall()

    return ContentListSuccess(data=[get_content_class(*c) for c in content])


@app.get("/content/{project}/{oid}")
def get_content(project: str, oid: str) -> ContentSuccess:
    content = con.execute(
        "SELECT oid, userid, title, meta, data FROM content WHERE project=? AND oid=?",
        (project, oid),
    ).fetchone()

    return ContentSuccess(data=get_content_class(*content))


@app.post("/content/{project}", responses={401: {"model": Error}})
def add_content(
    project: str, title: str, meta: str, data: bytes, token: str
) -> OidSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Validation failed")

    content = con.execute(
        "INSERT INTO content (userid, project, title, meta, data) VALUES(?, ?, ?, ?, ?)",
        (userid, project, title, meta, data),
    )
    con.commit()

    return OidSuccess(data=Oid(oid=content.lastrowid))


@app.put("/content/{project}/{oid}", responses={401: {"model": Error}})
def update_content(
    project: str, oid: str, title: str, meta: str, data: bytes, token: str
) -> PlainSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Validation failed")

    con.execute(
        "UPDATE content SET title=?, meta=?, data=? WHERE userid=? AND project=? AND oid=?",
        (title, meta, data, userid, project, oid),
    )
    con.commit()

    return PlainSuccess()


@app.delete("/content/{project}/{oid}", responses={401: {"model": Error}})
def delete_content(project: str, oid: str, token: str) -> PlainSuccess:
    userid = token_to_userid(con, token)

    if userid is None:
        return get_error(401, "Validation failed")

    if not own(con, oid, userid):
        return Error

    con.execute(
        "DELETE FROM content WHERE userid=? AND project=? AND oid=?",
        (userid, project, oid),
    )
    con.commit()

    return PlainSuccess()
