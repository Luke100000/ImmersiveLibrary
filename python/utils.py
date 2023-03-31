from starlette.responses import JSONResponse

from api_types import Error, Content


def token_to_userid(con, token):
    userid = con.execute(
        "SELECT userid FROM sessions WHERE token=?", (token,)
    ).fetchone()
    return None if userid is None else userid[0]


def register_session(con, userid, token):
    cur = con.cursor()
    cur.execute("DELETE FROM sessions WHERE userid=?", (userid,))
    cur.execute("INSERT INTO sessions (token, userid) VALUES (?, ?)", (token, userid))
    cur.close()
    con.commit()


def own(con, oid, userid):
    return (
        con.execute(
            "SELECT * FROM content WHERE userid=? AND oid=?",
            (userid, oid),
        ).rowcount
        > 0
    )


def get_error(status, message):
    return JSONResponse(status_code=status, content=Error(message=message).to_json())


def get_content_class(
    oid: int, userid: str, title: str, meta: str = None, data: bytes = None
):
    username = "WIP"  # todo
    return Content(
        oid=oid,
        username=username,
        title=title,
        meta="" if meta is None else meta,
        data="" if data is None else data,
    )
