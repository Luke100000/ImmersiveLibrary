import sqlite3

from python.main import (
    register_session,
    add_content,
    get_content,
    update_content,
    list_content,
)

token = "guest_token"

con = sqlite3.connect("database.db")
register_session(con, "123", token)
con.close()


# Insert test
oid = add_content("test", "Test object", "{}", "123DATA", token).data.oid
print(f"Data inserted with oid {oid}")

# Get test
print(get_content("test", oid))

# Get list test
print(list_content("test"))

# Rename test
update_content("test", oid, "Test object Renamed", "{}", "123DATA2", token)
print(get_content("test", oid))
