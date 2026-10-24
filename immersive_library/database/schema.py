from databases import Database

from immersive_library.database.migrations import run_migrations


async def create_user_tables(database: Database) -> None:
    async with database.connection() as connection:
        await connection.execute("BEGIN IMMEDIATE")
        try:
            await connection.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    oid INTEGER PRIMARY KEY AUTOINCREMENT,
                    google_userid CHAR,
                    username CHAR,
                    moderator INTEGER,
                    banned INTEGER
                )
            """)
            await connection.execute("""
                CREATE TABLE IF NOT EXISTS user_tokens (
                    oid INTEGER PRIMARY KEY AUTOINCREMENT,
                    token CHAR NOT NULL UNIQUE,
                    userid INTEGER NOT NULL
                )
            """)

            await connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS users_google_userid on users (google_userid)"
            )
            await connection.execute(
                "CREATE INDEX IF NOT EXISTS user_tokens_userid on user_tokens (userid)"
            )
        except BaseException:
            await connection.execute("ROLLBACK")
            raise
        else:
            await connection.execute("COMMIT")


async def initialize_database(database: Database) -> None:
    await create_user_tables(database)

    # Content
    await database.execute("""
        CREATE TABLE IF NOT EXISTS content (
            oid INTEGER PRIMARY KEY AUTOINCREMENT,
            userid INTEGER,
            project CHAR,
            title CHAR,
            version int DEFAULT 0,
            meta TEXT,
            data BLOB
        )
    """)
    await database.execute(
        "CREATE INDEX IF NOT EXISTS content_userid on content (userid)"
    )

    # Reports
    await database.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            userid INTEGER,
            contentid INTEGER REFERENCES content(oid) ON DELETE CASCADE,
            reason CHAR
        )
    """)
    await database.execute(
        "CREATE INDEX IF NOT EXISTS reports_userid on reports (userid)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS reports_contentid on reports (contentid)"
    )

    # Likes
    await database.execute(
        "CREATE TABLE IF NOT EXISTS likes (userid INTEGER, contentid INTEGER REFERENCES content(oid) ON DELETE CASCADE)"
    )
    await database.execute("CREATE INDEX IF NOT EXISTS likes_userid on likes (userid)")
    await database.execute(
        "CREATE INDEX IF NOT EXISTS likes_contentid on likes (contentid)"
    )

    # Tags
    await database.execute(
        "CREATE TABLE IF NOT EXISTS tags (contentid INTEGER REFERENCES content(oid) ON DELETE CASCADE, tag CHAR)"
    )
    await database.execute(
        "CREATE INDEX IF NOT EXISTS tags_contentid on tags (contentid)"
    )

    # Precomputation
    await database.execute("""
        CREATE TABLE IF NOT EXISTS precomputation (
            contentid INTEGER PRIMARY KEY REFERENCES content(oid) ON DELETE CASCADE,
            tags CHAR,
            likes INTEGER,
            reports INTEGER
        ) WITHOUT ROWID
    """)

    await run_migrations(database)
