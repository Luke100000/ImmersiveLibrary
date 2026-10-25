from databases import Database

from immersive_library.database.migrations import run_migrations
from immersive_library.database.migrations.snake_case import migrate_snake_case


async def create_user_tables(database: Database) -> None:
    async with database.connection() as connection:
        await connection.execute("BEGIN IMMEDIATE")
        try:
            await connection.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    oid INTEGER PRIMARY KEY AUTOINCREMENT,
                    google_user_id CHAR,
                    username CHAR,
                    moderator INTEGER,
                    banned INTEGER
                )
            """)
            await connection.execute("""
                CREATE TABLE IF NOT EXISTS user_tokens (
                    oid INTEGER PRIMARY KEY AUTOINCREMENT,
                    token CHAR NOT NULL UNIQUE,
                    user_id INTEGER NOT NULL
                )
            """)

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
    await database.execute("""
        CREATE TABLE IF NOT EXISTS content (
            oid INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            project CHAR,
            title CHAR,
            version int DEFAULT 0,
            meta TEXT,
            data BLOB
        )
    """)
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

    # Reports
    await database.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            user_id INTEGER,
            content_id INTEGER REFERENCES content(oid) ON DELETE CASCADE,
            reason CHAR
        )
    """)
    await database.execute(
        "CREATE INDEX IF NOT EXISTS reports_user_id on reports (user_id)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS reports_content_id on reports (content_id)"
    )

    # Likes
    await database.execute(
        "CREATE TABLE IF NOT EXISTS likes (user_id INTEGER, content_id INTEGER REFERENCES content(oid) ON DELETE CASCADE)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS likes_user_id on likes (user_id)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS likes_content_id on likes (content_id)"
    )

    # Tags
    await database.execute(
        "CREATE TABLE IF NOT EXISTS tags (content_id INTEGER REFERENCES content(oid) ON DELETE CASCADE, tag CHAR)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS tags_content_id on tags (content_id)"
    )

    # Precomputation
    await database.execute("""
        CREATE TABLE IF NOT EXISTS precomputation (
            content_id INTEGER PRIMARY KEY REFERENCES content(oid) ON DELETE CASCADE,
            tags CHAR,
            likes INTEGER,
            reports INTEGER
        ) WITHOUT ROWID
    """)

    await run_migrations(database)
