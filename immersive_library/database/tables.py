LEGACY_TIMESTAMP = 0

TABLES = {
    "users": """(
        oid INTEGER PRIMARY KEY AUTOINCREMENT,
        google_user_id CHAR,
        username CHAR,
        moderator INTEGER,
        banned INTEGER,
        created_at INTEGER NOT NULL DEFAULT (unixepoch())
    )""",
    "user_tokens": """(
        oid INTEGER PRIMARY KEY AUTOINCREMENT,
        token CHAR NOT NULL UNIQUE,
        user_id INTEGER NOT NULL,
        created_at INTEGER NOT NULL DEFAULT (unixepoch())
    )""",
    "content": """(
        oid INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        project CHAR,
        title CHAR,
        version int DEFAULT 0,
        meta TEXT,
        data BLOB,
        created_at INTEGER NOT NULL DEFAULT (unixepoch()),
        updated_at INTEGER NOT NULL DEFAULT (unixepoch())
    )""",
    # Collections reference shared assets without changing their ownership.
    "collections": """(
        oid INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(oid) ON DELETE CASCADE,
        project TEXT NOT NULL,
        title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 100),
        description TEXT NOT NULL DEFAULT '' CHECK(length(description) <= 2000),
        is_public INTEGER NOT NULL DEFAULT 0 CHECK(is_public IN (0, 1)),
        created_at INTEGER NOT NULL DEFAULT (unixepoch()),
        updated_at INTEGER NOT NULL DEFAULT (unixepoch())
    )""",
    "collection_items": """(
        collection_id INTEGER NOT NULL REFERENCES collections(oid) ON DELETE CASCADE,
        content_id INTEGER NOT NULL REFERENCES content(oid) ON DELETE CASCADE,
        created_at INTEGER NOT NULL DEFAULT (unixepoch()),
        PRIMARY KEY (collection_id, content_id)
    ) WITHOUT ROWID""",
    "reports": """(
        user_id INTEGER,
        content_id INTEGER REFERENCES content(oid) ON DELETE CASCADE,
        reason CHAR,
        created_at INTEGER NOT NULL DEFAULT (unixepoch())
    )""",
    "likes": """(
        user_id INTEGER,
        content_id INTEGER REFERENCES content(oid) ON DELETE CASCADE,
        created_at INTEGER NOT NULL DEFAULT (unixepoch())
    )""",
    "tags": """(
        content_id INTEGER REFERENCES content(oid) ON DELETE CASCADE,
        tag CHAR,
        created_at INTEGER NOT NULL DEFAULT (unixepoch())
    )""",
    "precomputation": """(
        content_id INTEGER PRIMARY KEY REFERENCES content(oid) ON DELETE CASCADE,
        tags CHAR,
        likes INTEGER,
        reports INTEGER
    ) WITHOUT ROWID""",
}


def create_table_sql(table: str, name: str | None = None) -> str:
    return f"CREATE TABLE IF NOT EXISTS {name or table} {TABLES[table]}"
