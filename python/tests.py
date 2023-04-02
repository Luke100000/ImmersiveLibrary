import json

from starlette.responses import JSONResponse

from python.utils import set_moderator, token_to_userid


def print_json(param: JSONResponse):
    if isinstance(param, JSONResponse):
        print(param.body.decode())
    else:
        # noinspection PyUnresolvedReferences
        print(json.dumps(param.dict()))


from python.main import (
    login_user,
    add_content,
    get_content,
    update_content,
    list_content,
    add_like,
    delete_like,
    add_tag,
    delete_tag,
    get_users,
    get_user,
    list_project_tags,
    list_content_tags,
    set_user,
    con,
)

token = "guest_token"

login_user(con, "123", "Warp", token)
con.commit()


# Insert test
contentid = add_content("test", "Test object", "{}", "123DATA", token).data.contentid
contentid_2 = add_content(
    "test", "Test object #2", "{}", "123DATA", token
).data.contentid
print(f"Data inserted with oid {contentid}")

# Get test
print_json(get_content("test", contentid))

# Get list test
print_json(list_content("test"))

# Rename test
print_json(
    update_content("test", contentid, "Test object Renamed", "{}", "123DATA2", token)
)
print_json(get_content("test", contentid))

# Like
print_json(add_like("test", contentid, token))
print_json(add_like("test2", contentid, token))
print_json(get_content("test", contentid))
print_json(add_like("test", contentid, token))

# Delete like
print_json(delete_like("test", contentid, token))
print_json(get_content("test", contentid))
print_json(delete_like("test", contentid, token))

# Tag
print_json(add_tag("test", contentid, "Tag1", token))
print_json(add_tag("test", contentid, "Tag2", token))
print_json(get_content("test", contentid))
print_json(add_tag("test", contentid, "Tag2", token))

# Untag
print_json(delete_tag("test", contentid, "Tag1", token))
print_json(get_content("test", contentid))
print_json(delete_tag("test", contentid, "Tag1", token))

# User
print_json(get_users("test"))
print_json(get_user("test", 1))

# Tags
print_json(list_project_tags("test"))
print_json(list_content_tags("test", contentid))

# Moderator tools
print_json(set_user(1, token, moderator=True))

# Make moderator
userid = token_to_userid(con, token)
set_moderator(con, userid, True)
con.commit()

print_json(set_user(userid, token, moderator=True))
print_json(set_user(userid, token, banned=True))
print_json(set_user(userid, token, purge=True))
