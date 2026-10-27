from databases import Database

from immersive_library.database.tables import LEGACY_TIMESTAMP, create_table_sql

TIMESTAMP_COLUMNS = {
    "users": ("created_at",),
    "user_tokens": ("created_at",),
    "content": ("created_at", "updated_at"),
    "collections": ("created_at", "updated_at"),
    "collection_items": ("created_at",),
    "reports": ("created_at",),
    "likes": ("created_at",),
    "tags": ("created_at",),
}


async def migrate_timestamps(database: Database) -> None:
    async with database.connection() as connection:
        # SQLite cannot add columns with a nonconstant default, so tables are rebuilt.
        # Dropping a parent table would cascade into its children unless keys are off,
        # which is only possible outside a transaction.
        await connection.execute("PRAGMA foreign_keys = OFF")
        try:
            await connection.execute("BEGIN IMMEDIATE")
            try:
                await _migrate(connection)
                if await connection.fetch_all("PRAGMA foreign_key_check"):
                    raise RuntimeError(
                        "Foreign key check failed during timestamp migration"
                    )
            except BaseException:
                await connection.execute("ROLLBACK")
                raise
            else:
                await connection.execute("COMMIT")
        finally:
            await connection.execute("PRAGMA foreign_keys = ON")


async def _table_columns(connection, table: str) -> list[str]:
    return [
        column["name"]
        for column in await connection.fetch_all(f'PRAGMA table_info("{table}")')
    ]


async def _migrate(connection) -> None:
    # Standardize the membership timestamp name before checking for missing columns.
    if "added_at" in await _table_columns(connection, "collection_items"):
        await connection.execute(
            "ALTER TABLE collection_items RENAME COLUMN added_at TO created_at"
        )

    for table, timestamps in TIMESTAMP_COLUMNS.items():
        columns = await _table_columns(connection, table)
        missing = [column for column in timestamps if column not in columns]
        if not missing:
            continue

        await connection.execute(create_table_sql(table, f"{table}_timestamps"))
        new_columns = await _table_columns(connection, f"{table}_timestamps")
        if dropped := set(columns) - set(new_columns):
            raise RuntimeError(f"Cannot migrate {table}: unknown columns {dropped}")

        # Keep rowids stable for tables without an explicit primary key.
        kept = columns if "oid" in columns else ["rowid", *columns]
        values = {
            column: (
                "created_at"
                if column == "updated_at" and "created_at" in columns
                else str(LEGACY_TIMESTAMP)
            )
            for column in missing
        }
        await connection.execute(
            f"INSERT INTO {table}_timestamps ({', '.join([*kept, *values])}) "
            f"SELECT {', '.join([*kept, *values.values()])} FROM {table}"
        )

        objects = await connection.fetch_all(
            "SELECT sql FROM sqlite_master WHERE tbl_name=:name "
            "AND type IN ('index', 'trigger') AND sql IS NOT NULL",
            {"name": table},
        )
        sequence = await connection.fetch_val(
            "SELECT seq FROM sqlite_sequence WHERE name=:name", {"name": table}
        )
        await connection.execute(f"DROP TABLE {table}")
        await connection.execute(f"ALTER TABLE {table}_timestamps RENAME TO {table}")
        for obj in objects:
            await connection.execute(obj["sql"])

        # Prevent AUTOINCREMENT from reusing ids of rows deleted before the rebuild.
        if sequence is not None:
            await connection.execute(
                "DELETE FROM sqlite_sequence WHERE name=:name AND seq < :seq",
                {"seq": sequence, "name": table},
            )
            await connection.execute(
                "INSERT INTO sqlite_sequence (name, seq) SELECT :name, :seq "
                "WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name=:name)",
                {"seq": sequence, "name": table},
            )
