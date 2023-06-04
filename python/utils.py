import base64
from sqlite3 import Connection, Cursor
from typing import List, Tuple

from starlette.responses import JSONResponse

from api_types import Error, Content, User, LiteContent, LiteUser


def get_base_select(data: bool):
    s = """
    SELECT c.oid,
           c.userid,
           c.title,
           c.version,
           users.username,
           c.meta,
           c.data,
           CASE WHEN liked_content.likes is NULL THEN 0 ELSE liked_content.likes END as likes,
           CASE WHEN tagged_content.tags is NULL THEN '' ELSE tagged_content.tags END as tags
    FROM content c
             INNER JOIN users ON c.userid = users.oid

             LEFT JOIN (SELECT likes.contentid, COUNT(*) as likes
                        FROM likes
                        GROUP BY likes.contentid) liked_content ON liked_content.contentid = c.oid

             LEFT JOIN (SELECT tags.contentid, GROUP_CONCAT(tag, ',') as tags
                        FROM tags
                        GROUP BY tags.contentid) tagged_content on tagged_content.contentid = c.oid

    """

    if not data:
        s = s.replace("c.meta,", "")
        s = s.replace("c.data,", "")

    return s


BASE_SELECT = get_base_select(True)
BASE_LITE_SELECT = get_base_select(False)


def token_to_userid(con: Connection, token: str) -> int:
    """
    Return the userid for a given token, or None if the token is invalid
    """
    if len(token) == 0:
        return None
    userid = con.execute("SELECT oid FROM users WHERE token=?", (token,)).fetchone()
    return None if userid is None else userid[0]


def get_count(con: Connection, query: str, params: Tuple[any]):
    return con.execute(query, params).fetchone()[0]


def exists(con: Connection, query: str, params: Tuple[any]):
    return get_count(con, query, params) > 0


def account_exists(con: Connection, google_userid: str) -> bool:
    """
    Checks if the account with the given google userid exists
    """
    return exists(
        con, "SELECT count(*) FROM users WHERE google_userid=?", (google_userid,)
    )


def user_exists(con: Connection, userid: int) -> bool:
    """
    Checks if the user with the given userid exists
    """
    return exists(con, "SELECT count(*) FROM users WHERE oid=?", (userid,))


def login_user(con: Connection, google_userid, username, token):
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

    con.commit()


def owns_content(con: Connection, contentid: int, userid: int) -> bool:
    """
    Checks if the user owns that content
    """
    return exists(
        con,
        "SELECT count(*) FROM content WHERE userid=? AND oid=?",
        (userid, contentid),
    )


def is_moderator(con: Connection, userid: int) -> bool:
    """
    Checks if the user is a moderator
    """
    return exists(
        con, "SELECT count(*) FROM users WHERE oid=? AND moderator=TRUE", (userid,)
    )


def is_banned(con: Connection, userid: int) -> bool:
    """
    Checks if the user is banned
    """
    return exists(
        con, "SELECT count(*) FROM users WHERE oid=? AND banned=TRUE", (userid,)
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


def has_liked(con, userid, contentid):
    """
    Checks if the given user has liked the content
    """
    return exists(
        con,
        "SELECT count(*) FROM likes WHERE userid=? AND contentid=?",
        (userid, contentid),
    )


def has_tag(con: Connection, contentid: int, tag: str) -> bool:
    """
    Checks if the given content has a given tag
    """
    return exists(
        con, "SELECT count(*) FROM tags WHERE tag=? AND contentid=?", (tag, contentid)
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


def get_likes(cur: Cursor, contentid: int) -> int:
    """
    Retrieves the total likes a content received
    """
    return get_count(cur, "SELECT COUNT(*) FROM likes WHERE contentid=?", (contentid,))


def get_liked_content(cur: Cursor, project: str, userid: int) -> List[Content]:
    """
    Retrieves all content liked by the given user in a project
    """
    content = cur.execute(
        BASE_LITE_SELECT
        + """
INNER JOIN likes on likes.userid=c.userid AND likes.contentid=c.oid
WHERE likes.userid=? AND c.project=?
        """,
        (userid, project),
    ).fetchall()
    return [get_lite_content_class(*c) for c in content]


def get_submissions(cur: Cursor, project: str, userid: int) -> List[Content]:
    """
    Retrieves all content submitted by a user in a project
    """
    content = cur.execute(
        BASE_LITE_SELECT
        + """
WHERE c.userid=? AND c.project=?
        """,
        (userid, project),
    ).fetchall()
    return [get_lite_content_class(*c) for c in content]


def get_tags(cur: Cursor, contentid: int) -> List[str]:
    """
    Get all tags for a given content
    """
    tags = cur.execute(
        "SELECT tag FROM tags WHERE contentid=?", (contentid,)
    ).fetchall()
    return [t[0] for t in tags]


def get_project_tags(cur: Cursor, project: str) -> List[str]:
    """
    Retrieves all distinct tags of a project
    """
    tags = cur.execute(
        "SELECT DISTINCT tag FROM tags INNER JOIN content ON tags.contentid=content.oid WHERE content.project=?",
        (project,),
    ).fetchall()
    return [t[0] for t in tags]


def get_lite_content_class(
    contentid: int,
    userid: str,
    title: str,
    version: int,
    username: str,
    likes: 0,
    tags: str,
):
    """
    Populates a lite content object
    """

    return LiteContent(
        contentid=contentid,
        userid=userid,
        username=username,
        likes=likes,
        tags=tags.split(",") if tags else [],
        title=title,
        version=version,
    )


def get_content_class(
    contentid: int,
    userid: str,
    title: str,
    version: int,
    username: str,
    meta: str,
    data: bytes,
    likes: 0,
    tags: str,
):
    """
    Populates a content object
    """

    return Content(
        contentid=contentid,
        userid=userid,
        username=username,
        likes=likes,
        tags=tags.split(",") if tags else [],
        title=title,
        version=version,
        meta=meta,
        data=base64.b64encode(data),
    )


def get_lite_user_class(
    userid: int,
    username: str,
    moderator: int,
    submission_count: int,
    likes_given: int,
    likes_received: int,
):
    """
    Populates a user object
    """
    return LiteUser(
        userid=userid,
        username=username,
        submission_count=submission_count,
        likes_given=likes_given,
        likes_received=likes_received,
        moderator=moderator > 0,
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
    likes_received = sum([c.likes for c in submissions])
    cur.close()
    return User(
        userid=userid,
        username=username,
        likes_received=likes_received,
        likes=likes,
        submissions=submissions,
        moderator=moderator > 0,
    )
