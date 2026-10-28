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
        title, tags, username, tokenize='unicode61 remove_diacritics 2', prefix='2 3'
    )
"""
SEARCH_TAGS = (
    "COALESCE((SELECT group_concat(tag, ' ') FROM tags WHERE content_id={id}), '')"
)
SEARCH_ROW = f"""
    SELECT content.oid, content.title, {SEARCH_TAGS.format(id="content.oid")}, users.username
    FROM content JOIN users ON users.oid=content.user_id
"""
SEARCH_TRIGGERS = {
    "content_search_insert": f"""
        AFTER INSERT ON content BEGIN
            INSERT INTO content_search (rowid, title, tags, username)
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


async def initialize_search(database: Database) -> None:
    await database.execute(SEARCH_TABLE)
    for name, trigger in SEARCH_TRIGGERS.items():
        await database.execute(f"CREATE TRIGGER IF NOT EXISTS {name} {trigger}")

    # The index is derived data, so it is rebuilt whenever it drifted from content.
    async with database.transaction():
        if await database.fetch_val(
            "SELECT (SELECT count(*) FROM content) != (SELECT count(*) FROM content_search)"
        ):
            await database.execute("DELETE FROM content_search")
            await database.execute(
                f"INSERT INTO content_search (rowid, title, tags, username) {SEARCH_ROW}"
            )


async def initialize_database(database: Database) -> None:
    for table in TABLES:
        await database.execute(create_table_sql(table))

    await run_migrations(database)

    for index in INDEXES:
        await database.execute(index)

    await initialize_search(database)
