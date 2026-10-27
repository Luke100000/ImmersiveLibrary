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
)


async def initialize_database(database: Database) -> None:
    for table in TABLES:
        await database.execute(create_table_sql(table))

    # Rebuilt tables lose their indexes, so they are created afterwards.
    await run_migrations(database)
    for index in INDEXES:
        await database.execute(index)
