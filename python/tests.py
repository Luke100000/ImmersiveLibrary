import sqlite3

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
)

token = "guest_token"

con = sqlite3.connect("database.db")
login_user(con, "123", "Warp", token)
con.commit()
con.close()


# Insert test
itemid = add_content("test", "Test object", "{}", "123DATA", token).data.itemid
itemid_2 = add_content("test", "Test object #2", "{}", "123DATA", token).data.itemid
print(f"Data inserted with oid {itemid}")

# Get test
print(get_content("test", itemid))

# Get list test
print(list_content("test"))

# Rename test
print(update_content("test", itemid, "Test object Renamed", "{}", "123DATA2", token))
print(get_content("test", itemid))


# Like
print(add_like("test", itemid, token))
print(add_like("test2", itemid, token))
print(get_content("test", itemid))
print(add_like("test", itemid, token))


# Delete like
print(delete_like("test", itemid, token))
print(get_content("test", itemid))
print(delete_like("test", itemid, token))


# Tag
print(add_tag("test", itemid, "Tag1", token))
print(add_tag("test", itemid, "Tag2", token))
print(get_content("test", itemid))
print(add_tag("test", itemid, "Tag2", token))


# Untag
print(delete_tag("test", itemid, "Tag1", token))
print(get_content("test", itemid))
print(delete_tag("test", itemid, "Tag1", token))

# User
print(get_users("test"))
print(get_user("test", 1))

# Tags
print(list_project_tags("test"))
print(list_item_tags("test", itemid))
