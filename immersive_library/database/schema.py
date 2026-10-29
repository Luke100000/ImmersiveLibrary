from databases import Database

from immersive_library.database.migrations import run_migrations
from immersive_library.database.tables import TABLES, create_table_sql

INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS users_google_user_id ON users (google_user_id)",
    "CREATE INDEX IF NOT EXISTS user_tokens_user_id ON user_tokens (user_id)",
    "CREATE INDEX IF NOT EXISTS content_user_id ON content (user_id)",
    "CREATE INDEX IF NOT EXISTS content_project ON content (project)",
    "CREATE INDEX IF NOT EXISTS content_project_title ON content (project, title)",
    "CREATE INDEX IF NOT EXISTS content_project_user_id ON content (project, user_id)",
    "CREATE INDEX IF NOT EXISTS content_project_length ON content (project, length(data))",
    "CREATE INDEX IF NOT EXISTS collections_user_id_project ON collections (user_id, project)",
    "CREATE INDEX IF NOT EXISTS collection_items_content_id ON collection_items (content_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS reports_unique ON reports (user_id, content_id, reason)",
    "CREATE INDEX IF NOT EXISTS reports_content_id ON reports (content_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS likes_unique ON likes (user_id, content_id)",
    "CREATE INDEX IF NOT EXISTS likes_content_id ON likes (content_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS tags_unique ON tags (content_id, tag)",
    "CREATE INDEX IF NOT EXISTS likes_created_at ON likes (created_at)",
)

# Keyword index over the fields free-text search matches. The rowid is the content ID.
SEARCH_TABLE = """
    CREATE VIRTUAL TABLE IF NOT EXISTS content_search USING fts5(
        title, tags, username, description,
        tokenize='unicode61 remove_diacritics 2', prefix='2 3'
    )
"""
SEARCH_TAGS = (
    "COALESCE((SELECT group_concat(tag, ' ') FROM tags WHERE content_id={id}), '')"
)
SEARCH_DESCRIPTION = """COALESCE((
    SELECT description FROM content_descriptions WHERE content_id={id} AND error IS NULL
), '')"""
SEARCH_ROW = f"""
    SELECT content.oid, content.title, {SEARCH_TAGS.format(id="content.oid")},
           users.username, {SEARCH_DESCRIPTION.format(id="content.oid")}
    FROM content JOIN users ON users.oid=content.user_id
"""
SEARCH_COLUMNS = "(rowid, title, tags, username, description)"
SEARCH_TRIGGERS = {
    "content_search_insert": f"""
        AFTER INSERT ON content BEGIN
            INSERT INTO content_search {SEARCH_COLUMNS}
            {SEARCH_ROW} WHERE content.oid=NEW.oid;
        END""",
    "content_search_update": """
        AFTER UPDATE OF title, user_id ON content BEGIN
            UPDATE content_search SET title=NEW.title,
                username=(SELECT username FROM users WHERE oid=NEW.user_id)
            WHERE rowid=NEW.oid;
        END""",
    "content_search_delete": """
        AFTER DELETE ON content BEGIN
            DELETE FROM content_search WHERE rowid=OLD.oid;
        END""",
    "content_search_tag_insert": f"""
        AFTER INSERT ON tags BEGIN
            UPDATE content_search SET tags={SEARCH_TAGS.format(id="NEW.content_id")}
            WHERE rowid=NEW.content_id;
        END""",
    "content_search_tag_delete": f"""
        AFTER DELETE ON tags BEGIN
            UPDATE content_search SET tags={SEARCH_TAGS.format(id="OLD.content_id")}
            WHERE rowid=OLD.content_id;
        END""",
    "content_search_username": """
        AFTER UPDATE OF username ON users BEGIN
            UPDATE content_search SET username=NEW.username
            WHERE rowid IN (SELECT oid FROM content WHERE user_id=NEW.oid);
        END""",
}
SEARCH_TRIGGERS |= {
    f"content_search_description_{operation}": f"""
        AFTER {operation.upper()} ON content_descriptions BEGIN
            UPDATE content_search
            SET description={SEARCH_DESCRIPTION.format(id=f"{row}.content_id")}
            WHERE rowid={row}.content_id;
        END"""
    for operation, row in [("insert", "NEW"), ("update", "NEW"), ("delete", "OLD")]
}

# A description is removed as soon as its asset changes, so stale text is never used.
DESCRIPTION_TRIGGERS = {
    "content_descriptions_content_changed": """
        AFTER UPDATE OF project, title, meta, data, version ON content BEGIN
            DELETE FROM content_descriptions WHERE content_id=NEW.oid;
        END""",
    "content_descriptions_tag_insert": """
        AFTER INSERT ON tags BEGIN
            DELETE FROM content_descriptions WHERE content_id IN (NEW.content_id);
        END""",
    "content_descriptions_tag_delete": """
        AFTER DELETE ON tags BEGIN
            DELETE FROM content_descriptions WHERE content_id IN (OLD.content_id);
        END""",
    "content_descriptions_tag_update": """
        AFTER UPDATE ON tags BEGIN
            DELETE FROM content_descriptions WHERE content_id IN (OLD.content_id, NEW.content_id);
        END""",
}


async def create_triggers(database: Database, triggers: dict[str, str]) -> None:
    for name, trigger in triggers.items():
        await database.execute(f"DROP TRIGGER IF EXISTS {name}")
        await database.execute(f"CREATE TRIGGER {name} {trigger}")


def normalized(sql: str | None) -> str:
    return " ".join((sql or "").replace("IF NOT EXISTS ", "").split())


async def initialize_search(database: Database) -> None:
    current = await database.fetch_val(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='content_search'"
    )
    if current is not None and normalized(current) != normalized(SEARCH_TABLE):
        await database.execute("DROP TABLE content_search")
    await database.execute(SEARCH_TABLE)
    await create_triggers(database, SEARCH_TRIGGERS)

    async with database.transaction():
        if await database.fetch_val(
            "SELECT (SELECT count(*) FROM content) != (SELECT count(*) FROM content_search)"
        ):
            await database.execute("DELETE FROM content_search")
            await database.execute(
                f"INSERT INTO content_search {SEARCH_COLUMNS} {SEARCH_ROW}"
            )


async def initialize_database(database: Database) -> None:
    for table in TABLES:
        await database.execute(create_table_sql(table))

    await run_migrations(database)

    for index in INDEXES:
        await database.execute(index)

    await initialize_search(database)
    await create_triggers(database, DESCRIPTION_TRIGGERS)
