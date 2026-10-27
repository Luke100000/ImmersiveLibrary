from databases import Database

from immersive_library.database.migrations.rebuild import rebuild_tables


async def run_migrations(database: Database) -> None:
    await rebuild_tables(database)
