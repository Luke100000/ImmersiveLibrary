from databases import Database

from immersive_library.database.migrations.rebuild import rebuild_tables


async def run_migrations(database: Database) -> None:
    await rebuild_tables(database)

    # Old token auth is no longer supported
    await database.execute(
        "DELETE FROM user_tokens WHERE length(token) != 64 OR token GLOB '*[^0-9a-f]*'"
    )
