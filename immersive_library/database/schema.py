from databases import Database

from immersive_library.database.migrations import run_migrations
from immersive_library.database.migrations.snake_case import migrate_snake_case
from immersive_library.database.tables import create_table_sql


async def create_user_tables(database: Database) -> None:
    async with database.connection() as connection:
        await connection.execute("BEGIN IMMEDIATE")
        try:
            await connection.execute(create_table_sql("users"))
            await connection.execute(create_table_sql("user_tokens"))

            await connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS users_google_user_id on users (google_user_id)"
            )
            await connection.execute(
                "CREATE INDEX IF NOT EXISTS user_tokens_user_id on user_tokens (user_id)"
            )
        except BaseException:
            await connection.execute("ROLLBACK")
            raise
        else:
            await connection.execute("COMMIT")


async def initialize_database(database: Database) -> None:
    # Existing columns must be renamed before creating indexes against the new names.
    await migrate_snake_case(database)
    await create_user_tables(database)

    # Content
    await database.execute(create_table_sql("content"))
    await database.execute(
        "CREATE INDEX IF NOT EXISTS content_user_id on content (user_id)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS content_project ON content (project)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS content_project_title ON content (project, title)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS content_project_user_id ON content (project, user_id)"
    )

    # Collections
    await database.execute(create_table_sql("collections"))
    await database.execute(
        "CREATE INDEX IF NOT EXISTS collections_user_id_project ON collections (user_id, project)"
    )
    await database.execute(create_table_sql("collection_items"))
    await database.execute(
        "CREATE INDEX IF NOT EXISTS collection_items_content_id ON collection_items (content_id)"
    )

    # Reports
    await database.execute(create_table_sql("reports"))
    await database.execute(
        "CREATE INDEX IF NOT EXISTS reports_user_id on reports (user_id)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS reports_content_id on reports (content_id)"
    )

    # Likes
    await database.execute(create_table_sql("likes"))
    await database.execute(
        "CREATE INDEX IF NOT EXISTS likes_user_id on likes (user_id)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS likes_content_id on likes (content_id)"
    )

    # Tags
    await database.execute(create_table_sql("tags"))
    await database.execute(
        "CREATE INDEX IF NOT EXISTS tags_content_id on tags (content_id)"
    )

    # Precomputation
    await database.execute(create_table_sql("precomputation"))

    await run_migrations(database)
