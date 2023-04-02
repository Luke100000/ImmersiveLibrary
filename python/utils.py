from sqlite3 import Connection, Cursor
from typing import List

from starlette.responses import JSONResponse

from api_types import Error, Content, User


def token_to_userid(con: Connection, token: str) -> int:
    """
    Return the userid for a given token, or None if the token is invalid
    """
    if len(token) == 0:
        return None
    userid = con.execute("SELECT oid FROM users WHERE token=?", (token,)).fetchone()
    return None if userid is None else userid[0]


def account_exists(con: Connection, google_userid: str) -> bool:
    """
    Checks if the account with the given google userid exists
    """
    return (
        con.execute(
            "SELECT count(*) FROM users WHERE google_userid=?", (google_userid,)
        ).fetchone()[0]
        > 0
    )


def user_exists(con: Connection, userid: int) -> bool:
    """
    Checks if the user with the given userid exists
    """
    return (
        con.execute("SELECT count(*) FROM users WHERE oid=?", (userid,)).fetchone()[0]
        > 0
    )


def login_user(con, google_userid, username, token):
    """
    Logins the user, creating an account of necessary and updating username and token
    """
    # Invalidate same tokens, the token has to be unique
    con.execute(
        "UPDATE users SET token='' WHERE token=?",
        (token,),
    )

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


def owns_content(con: Connection, itemid: int, userid: int) -> bool:
    """
    Checks if the user owns that content
    """
    return (
        con.execute(
            "SELECT count(*) FROM content WHERE userid=? AND oid=?",
            (userid, itemid),
        ).fetchone()[0]
        > 0
    )


def is_moderator(con: Connection, userid: int) -> bool:
    """
    Checks if the user is a moderator
    """
    return (
        con.execute(
            "SELECT count(*) FROM users WHERE oid=? AND moderator=TRUE",
            (userid,),
        ).fetchone()[0]
        > 0
    )


def is_banned(con: Connection, userid: int) -> bool:
    """
    Checks if the user is banned
    """
    return (
        con.execute(
            "SELECT count(*) FROM users WHERE oid=? AND banned=TRUE",
            (userid,),
        ).fetchone()[0]
        > 0
    )


def set_moderator(con, userid, moderator):
    """
    Sets moderator status
    """
    con.execute("UPDATE users SET moderator=? WHERE oid=?", (moderator, userid))


def set_banned(con, userid, banned):
    """
    Sets banned status
    """
    con.execute("UPDATE users SET banned=?, token='' WHERE oid=?", (banned, userid))


# todo swap parameters
# todo why itemid, its content
def has_liked(con, itemid, userid):
    """
    Checks if the given user has liked the content
    """
    return (
        con.execute(
            "SELECT count(*) FROM likes WHERE userid=? AND itemid=?",
            (userid, itemid),
        ).fetchone()[0]
        > 0
    )


def has_tag(con: Connection, itemid: int, tag: str) -> bool:
    """
    Checks if the given item has a given tag
    """
    return (
        con.execute(
            "SELECT count(*) FROM tags WHERE tag=? AND itemid=?",
            (tag, itemid),
        ).fetchone()[0]
        > 0
    )


def get_error(status: int, message: str) -> JSONResponse:
    """
    Wrap a status and message into a JSON
    """
    return JSONResponse(status_code=status, content=Error(message=message).to_json())


def get_username(cur: Cursor, userid: int) -> str:
    """
    Retrieves the username of a user
    """
    username = cur.execute(
        "SELECT username FROM users WHERE oid=?", (userid,)
    ).fetchone()
    return None if username is None else username[0]


def get_likes(cur: Cursor, itemid: int) -> int:
    """
    Retrieves the total likes a content received
    """
    return cur.execute(
        "SELECT COUNT(*) FROM likes WHERE itemid=?", (itemid,)
    ).fetchone()[0]


def get_liked_content(cur: Cursor, project: str, userid: int) -> List[Content]:
    """
    Retrieves all content liked by the given user in a project
    """
    content = cur.execute(
        "SELECT content.oid, content.userid, content.title FROM content INNER JOIN likes ON content.userid=likes.userid WHERE likes.userid=? AND content.project=?",
        (userid, project),
    ).fetchall()
    return [get_content_class(cur, *c) for c in content]


def get_submissions(cur: Cursor, project: str, userid: int) -> List[Content]:
    """
    Retrieves all content submitted by a user in a project
    """
    content = cur.execute(
        "SELECT oid, userid, title FROM content WHERE userid=? AND project=?",
        (userid, project),
    ).fetchall()
    return [get_content_class(cur, *c) for c in content]


def get_tags(cur: Cursor, itemid: int) -> List[str]:
    """
    Get all tags for a given content
    """
    tags = cur.execute("SELECT tag FROM tags WHERE itemid=?", (itemid,)).fetchall()
    return [t[0] for t in tags]


def get_project_tags(cur: Cursor, project: str) -> List[str]:
    """
    Retrieves all distinct tags of a project
    """
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
    """
    Populates a content object
    """
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
    """
    Populates a user object
    """
    cur = con.cursor()
    submissions = get_submissions(cur, project, userid)
    likes = get_liked_content(cur, project, userid)
    liked_received = sum([c.likes for c in submissions])
    cur.close()
    return User(
        userid=userid,
        username=username,
        liked_received=liked_received,
        likes=likes,
        submissions=submissions,
        moderator=moderator > 0,
    )
