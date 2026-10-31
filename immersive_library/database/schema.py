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
    "CREATE INDEX IF NOT EXISTS tags_tag_content_id ON tags (tag, content_id)",
    "CREATE INDEX IF NOT EXISTS likes_created_at ON likes (created_at)",
    "CREATE INDEX IF NOT EXISTS precomputation_likes ON precomputation (project, likes)",
    "CREATE INDEX IF NOT EXISTS precomputation_popular ON precomputation (project, recent_likes, likes)",
    "CREATE INDEX IF NOT EXISTS precomputation_hot_rank ON precomputation (project, hot_rank)",
    "CREATE INDEX IF NOT EXISTS precomputation_quality_rank ON precomputation (project, quality_rank)",
    "CREATE INDEX IF NOT EXISTS collections_project_quality_rank ON collections (project, quality_rank)",
    "CREATE INDEX IF NOT EXISTS content_descriptions_dirty ON content_descriptions (content_id) WHERE dirty > 0",
    "CREATE INDEX IF NOT EXISTS content_embeddings_dirty ON content_embeddings (content_id) WHERE dirty > 0",
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
    SELECT description FROM content_descriptions WHERE content_id={id}
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

COLLECTION_SEARCH_TABLE = """
    CREATE VIRTUAL TABLE IF NOT EXISTS collection_search USING fts5(
        title, username, description,
        tokenize='unicode61 remove_diacritics 2', prefix='2 3'
    )
"""
COLLECTION_SEARCH_ROW = """
    SELECT collections.oid, collections.title, users.username, collections.description
    FROM collections JOIN users ON users.oid=collections.user_id
"""
COLLECTION_SEARCH_COLUMNS = "(rowid, title, username, description)"
COLLECTION_SEARCH_TRIGGERS = {
    "collection_search_insert": f"""
        AFTER INSERT ON collections BEGIN
            INSERT INTO collection_search {COLLECTION_SEARCH_COLUMNS}
            {COLLECTION_SEARCH_ROW} WHERE collections.oid=NEW.oid;
        END""",
    "collection_search_update": """
        AFTER UPDATE OF title, description, user_id ON collections BEGIN
            UPDATE collection_search SET title=NEW.title, description=NEW.description,
                username=(SELECT username FROM users WHERE oid=NEW.user_id)
            WHERE rowid=NEW.oid;
        END""",
    "collection_search_delete": """
        AFTER DELETE ON collections BEGIN
            DELETE FROM collection_search WHERE rowid=OLD.oid;
        END""",
    "collection_search_username": """
        AFTER UPDATE OF username ON users BEGIN
            UPDATE collection_search SET username=NEW.username
            WHERE rowid IN (SELECT oid FROM collections WHERE user_id=NEW.oid);
        END""",
}

COLLECTION_MEMBERSHIP_TRIGGERS = {
    f"collection_membership_{operation}": f"""
        AFTER {operation.upper()} ON collection_items BEGIN
            UPDATE collections SET updated_at=unixepoch()
            WHERE oid={row}.collection_id;
        END"""
    for operation, row in [("insert", "NEW"), ("delete", "OLD")]
}


def mark_dirty(content_id: str, table: str, column: str) -> str:
    return f"""
        INSERT INTO {table} (content_id)
        SELECT oid FROM content WHERE oid = {content_id}
        ON CONFLICT DO UPDATE SET dirty = dirty + 1, {column} = NULL, error = NULL;"""


DESCRIPTION = ("content_descriptions", "description")
EMBEDDING = ("content_embeddings", "vector")

# Descriptions read the title, tags, metadata and the rendered image.
# Embeddings read only the rendered data.
ANALYSIS_TRIGGERS = {
    "analysis_content_insert": f"""
        AFTER INSERT ON content BEGIN
            {mark_dirty("NEW.oid", *DESCRIPTION)}
            {mark_dirty("NEW.oid", *EMBEDDING)}
        END""",
    "analysis_description_content_changed": f"""
        AFTER UPDATE OF title, meta, data ON content BEGIN
            {mark_dirty("NEW.oid", *DESCRIPTION)}
        END""",
    "analysis_embedding_content_changed": f"""
        AFTER UPDATE OF data ON content BEGIN
            {mark_dirty("NEW.oid", *EMBEDDING)}
        END""",
    "analysis_description_tag_insert": f"""
        AFTER INSERT ON tags BEGIN
            {mark_dirty("NEW.content_id", *DESCRIPTION)}
        END""",
    "analysis_description_tag_delete": f"""
        AFTER DELETE ON tags BEGIN
            {mark_dirty("OLD.content_id", *DESCRIPTION)}
        END""",
    "analysis_description_tag_update": f"""
        AFTER UPDATE ON tags BEGIN
            {mark_dirty("OLD.content_id", *DESCRIPTION)}
            {mark_dirty("NEW.content_id", *DESCRIPTION)}
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


async def initialize_collection_search(database: Database) -> None:
    await database.execute(COLLECTION_SEARCH_TABLE)
    await create_triggers(database, COLLECTION_SEARCH_TRIGGERS)

    async with database.transaction():
        if await database.fetch_val(
            "SELECT (SELECT count(*) FROM collections) != (SELECT count(*) FROM collection_search)"
        ):
            await database.execute("DELETE FROM collection_search")
            await database.execute(
                f"INSERT INTO collection_search {COLLECTION_SEARCH_COLUMNS} {COLLECTION_SEARCH_ROW}"
            )


async def initialize_database(database: Database) -> None:
    for table in TABLES:
        await database.execute(create_table_sql(table))

    await run_migrations(database)

    for index in INDEXES:
        await database.execute(index)

    await initialize_search(database)
    await initialize_collection_search(database)
    await create_triggers(database, COLLECTION_MEMBERSHIP_TRIGGERS)
    await create_triggers(database, ANALYSIS_TRIGGERS)
