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
    list_item_tags,
    set_user,
    con,
)

token = "guest_token"

login_user(con, "123", "Warp", token)
con.commit()


# Insert test
itemid = add_content("test", "Test object", "{}", "123DATA", token).data.itemid
itemid_2 = add_content("test", "Test object #2", "{}", "123DATA", token).data.itemid
print(f"Data inserted with oid {itemid}")

# Get test
print_json(get_content("test", itemid))

# Get list test
print_json(list_content("test"))

# Rename test
print_json(
    update_content("test", itemid, "Test object Renamed", "{}", "123DATA2", token)
)
print_json(get_content("test", itemid))

# Like
print_json(add_like("test", itemid, token))
print_json(add_like("test2", itemid, token))
print_json(get_content("test", itemid))
print_json(add_like("test", itemid, token))

# Delete like
print_json(delete_like("test", itemid, token))
print_json(get_content("test", itemid))
print_json(delete_like("test", itemid, token))

# Tag
print_json(add_tag("test", itemid, "Tag1", token))
print_json(add_tag("test", itemid, "Tag2", token))
print_json(get_content("test", itemid))
print_json(add_tag("test", itemid, "Tag2", token))

# Untag
print_json(delete_tag("test", itemid, "Tag1", token))
print_json(get_content("test", itemid))
print_json(delete_tag("test", itemid, "Tag1", token))

# User
print_json(get_users("test"))
print_json(get_user("test", 1))

# Tags
print_json(list_project_tags("test"))
print_json(list_item_tags("test", itemid))

# Moderator tools
print_json(set_user(1, token, moderator=True))

# Make moderator
userid = token_to_userid(con, token)
set_moderator(con, userid, True)
con.commit()

print_json(set_user(userid, token, moderator=True))
print_json(set_user(userid, token, banned=True))
print_json(set_user(userid, token, purge=True))
