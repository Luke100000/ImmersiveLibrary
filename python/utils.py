from sqlite3 import Connection, Cursor
from typing import List

from starlette.responses import JSONResponse

from api_types import Error, Content, User


def token_to_userid(con, token):
    userid = con.execute("SELECT oid FROM users WHERE token=?", (token,)).fetchone()
    return None if userid is None else userid[0]


def exists_userid(con, google_userid):
    return (
        con.execute(
            "SELECT count(*) FROM users WHERE google_userid=?", (google_userid,)
        ).fetchone()[0]
        > 0
    )


def login_user(con, google_userid, username, token):
    if exists_userid(con, google_userid):
        con.execute(
            "UPDATE users SET username=?, token=? WHERE google_userid=?",
            (username, token, google_userid),
        )
    else:
        con.execute(
            "INSERT INTO users (google_userid, token, username, moderator) VALUES (?, ?, ?, FALSE)",
            (google_userid, token, username),
        )


def own(con, oid, userid):
    return (
        con.execute(
            "SELECT count(*) FROM content WHERE userid=? AND oid=?",
            (userid, oid),
        ).fetchone()[0]
        > 0
    )


def has_liked(con, oid, userid):
    return (
        con.execute(
            "SELECT count(*) FROM likes WHERE userid=? AND id=?",
            (userid, oid),
        ).fetchone()[0]
        > 0
    )


def has_tag(con, oid, tag):
    return (
        con.execute(
            "SELECT count(*) FROM tags WHERE tag=? AND id=?",
            (tag, oid),
        ).fetchone()[0]
        > 0
    )


def get_error(status, message):
    return JSONResponse(status_code=status, content=Error(message=message).to_json())


def get_username(cur, userid):
    username = cur.execute(
        "SELECT username FROM users WHERE oid=?", (userid,)
    ).fetchone()
    return None if username is None else username[0]


def get_likes(cur, oid):
    likes = cur.execute("SELECT COUNT(*) FROM likes WHERE id=?", (oid,)).fetchone()
    return None if likes is None else likes[0]


def get_likes_received(submissions: List[Content]):
    return sum([c.likes for c in submissions])


def get_likes_for_user(cur, project, userid):
    content = cur.execute(
        "SELECT content.oid, content.userid, content.title FROM content INNER JOIN likes ON content.userid=likes.userid WHERE likes.userid=? AND content.project=?",
        (userid, project),
    ).fetchall()
    return [get_content_class(cur, *c) for c in content]


def get_submissions(cur, project, userid):
    content = cur.execute(
        "SELECT oid, userid, title FROM content WHERE userid=? AND project=?",
        (userid, project),
    ).fetchall()
    return [get_content_class(cur, *c) for c in content]


def get_tags(cur, oid):
    tags = cur.execute("SELECT tag FROM tags WHERE id=?", (oid,)).fetchall()
    return [t[0] for t in tags]


def get_project_tags(cur, project):
    tags = cur.execute(
        "SELECT DISTINCT tag FROM tags INNER JOIN content ON tags.id=content.oid WHERE content.project=?",
        (project,),
    ).fetchall()
    return [t[0] for t in tags]


def get_content_class(
    cur: Cursor,
    oid: int,
    userid: str,
    title: str,
    meta: str = None,
    data: bytes = None,
):
    username = get_username(cur, userid)
    likes = get_likes(cur, oid)
    tags = get_tags(cur, oid)
    return Content(
        oid=oid,
        username=username,
        likes=likes,
        tags=tags,
        title=title,
        meta="" if meta is None else meta,
        data="" if data is None else data,
    )


def get_user_class(
    con: Connection, project: str, userid: int, username: str, moderator: int
):
    cur = con.cursor()
    submissions = get_submissions(cur, project, userid)
    likes = get_likes_for_user(cur, project, userid)
    liked_received = get_likes_received(submissions)
    cur.close()
    return User(
        userid=userid,
        username=username,
        liked_received=liked_received,
        likes=likes,
        submissions=submissions,
        moderator=moderator > 0,
    )
