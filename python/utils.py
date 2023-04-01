from sqlite3 import Connection, Cursor
from typing import List

from starlette.responses import JSONResponse

from api_types import Error, Content, User


def token_to_userid(con, token):
    if len(token) == 0:
        return None
    userid = con.execute("SELECT oid FROM users WHERE token=?", (token,)).fetchone()
    return None if userid is None else userid[0]


def account_exists(con, google_userid):
    return (
        con.execute(
            "SELECT count(*) FROM users WHERE google_userid=?", (google_userid,)
        ).fetchone()[0]
        > 0
    )


def user_exists(con, userid):
    return (
        con.execute("SELECT count(*) FROM users WHERE oid=?", (userid,)).fetchone()[0]
        > 0
    )


def login_user(con, google_userid, username, token):
    if account_exists(con, google_userid):
        con.execute(
            "UPDATE users SET username=?, token=? WHERE google_userid=?",
            (username, token, google_userid),
        )
    else:
        con.execute(
            "INSERT INTO users (google_userid, token, username, moderator, banned) VALUES (?, ?, ?, FALSE, FALSE)",
            (google_userid, token, username),
        )


def own(con, itemid, userid):
    return (
        con.execute(
            "SELECT count(*) FROM content WHERE userid=? AND oid=?",
            (userid, itemid),
        ).fetchone()[0]
        > 0
    )


def is_moderator(con, userid):
    return (
        con.execute(
            "SELECT count(*) FROM users WHERE oid=? AND moderator=TRUE",
            (userid,),
        ).fetchone()[0]
        > 0
    )


def is_banned(con, userid):
    return (
        con.execute(
            "SELECT count(*) FROM users WHERE oid=? AND banned=TRUE",
            (userid,),
        ).fetchone()[0]
        > 0
    )


def set_moderator(con, userid, moderator):
    con.execute("UPDATE users SET moderator=? WHERE oid=?", (moderator, userid))


def set_banned(con, userid, banned):
    con.execute("UPDATE users SET banned=?, token='' WHERE oid=?", (banned, userid))


def has_liked(con, itemid, userid):
    return (
        con.execute(
            "SELECT count(*) FROM likes WHERE userid=? AND itemid=?",
            (userid, itemid),
        ).fetchone()[0]
        > 0
    )


def has_tag(con, itemid, tag):
    return (
        con.execute(
            "SELECT count(*) FROM tags WHERE tag=? AND itemid=?",
            (tag, itemid),
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


def get_likes(cur, itemid):
    likes = cur.execute(
        "SELECT COUNT(*) FROM likes WHERE itemid=?", (itemid,)
    ).fetchone()
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


def get_tags(cur, itemid):
    tags = cur.execute("SELECT tag FROM tags WHERE itemid=?", (itemid,)).fetchall()
    return [t[0] for t in tags]


def get_project_tags(cur, project):
    tags = cur.execute(
        "SELECT DISTINCT tag FROM tags INNER JOIN content ON tags.itemid=content.oid WHERE content.project=?",
        (project,),
    ).fetchall()
    return [t[0] for t in tags]


def get_content_class(
    cur: Cursor,
    itemid: int,
    userid: str,
    title: str,
    meta: str = None,
    data: bytes = None,
):
    username = get_username(cur, userid)
    likes = get_likes(cur, itemid)
    tags = get_tags(cur, itemid)
    return Content(
        itemid=itemid,
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
