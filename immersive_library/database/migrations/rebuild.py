import re

from databases import Database

from immersive_library.database.tables import (
    LEGACY_TIMESTAMP,
    TABLES,
    create_table_sql,
)

# Columns renamed since the original schema.
LEGACY_NAMES = {
    "userid": "user_id",
    "contentid": "content_id",
    "google_userid": "google_user_id",
}
# Columns whose values move to another table during the rebuild.
MOVED_COLUMNS = {"users": ("token",)}
# Must match the unique indexes in schema.py.
UNIQUE_KEYS = {
    "likes": ("user_id", "content_id"),
    "reports": ("user_id", "content_id", "reason"),
    "tags": ("content_id", "tag"),
}


async def rebuild_tables(database: Database) -> None:
    async with database.connection() as connection:
        # SQLite cannot add constraints or columns with a nonconstant default, so
        # tables whose definition differs from tables.py are rebuilt.
        # Dropping a parent table would cascade into its children unless keys are off,
        # which is only possible outside a transaction.
        await connection.execute("PRAGMA foreign_keys = OFF")
        try:
            await connection.execute("BEGIN IMMEDIATE")
            try:
                if await _rebuild(connection) and await connection.fetch_all(
                    "PRAGMA foreign_key_check"
                ):
                    raise RuntimeError("Foreign key check failed during table rebuild")
            except BaseException:
                await connection.execute("ROLLBACK")
                raise
            else:
                await connection.execute("COMMIT")
        finally:
            await connection.execute("PRAGMA foreign_keys = ON")


def _definition(sql: str) -> str:
    # SQLite keeps the original statement, so compare it from the column list on.
    return re.sub(r"\s+", " ", sql[sql.index("(") :]).strip()


async def _table_columns(connection, table: str) -> list[str]:
    return [
        column["name"]
        for column in await connection.fetch_all(f'PRAGMA table_info("{table}")')
    ]


async def _rebuild(connection) -> bool:
    rebuilt = False
    for table, definition in TABLES.items():
        current = await connection.fetch_val(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=:name",
            {"name": table},
        )
        if _definition(current) == _definition(definition):
            continue
        rebuilt = True

        columns = await _table_columns(connection, table)
        if table == "users" and "token" in columns:
            await connection.execute(
                "INSERT OR IGNORE INTO user_tokens (token, user_id) "
                "SELECT token, oid FROM users WHERE token IS NOT NULL AND token != ''"
            )

        await connection.execute(create_table_sql(table, f"{table}_rebuild"))
        new_columns = await _table_columns(connection, f"{table}_rebuild")
        sources = {
            LEGACY_NAMES.get(column, column): column
            for column in columns
            if column not in MOVED_COLUMNS.get(table, ())
        }
        if dropped := set(sources) - set(new_columns):
            raise RuntimeError(f"Cannot rebuild {table}: unknown columns {dropped}")

        # Keep rowids stable for tables without an explicit primary key.
        if "oid" not in sources and "WITHOUT ROWID" not in current.upper():
            sources = {"rowid": "rowid", **sources}
        if "created_at" in new_columns:
            sources.setdefault("created_at", str(LEGACY_TIMESTAMP))
        if "updated_at" in new_columns:
            sources.setdefault("updated_at", sources["created_at"])

        # Drop rows the cascades would have deleted and duplicates the unique
        # indexes would reject, keeping the oldest row.
        conditions = [
            f"{sources[key['from']]} IN (SELECT {key['to']} FROM {key['table']})"
            for key in await connection.fetch_all(
                f"PRAGMA foreign_key_list({table}_rebuild)"
            )
            if key["on_delete"] == "CASCADE"
        ]
        if table in UNIQUE_KEYS:
            keys = ", ".join(sources[column] for column in UNIQUE_KEYS[table])
            conditions.append(
                f"rowid IN (SELECT MIN(rowid) FROM {table} GROUP BY {keys})"
            )
        await connection.execute(
            f"INSERT INTO {table}_rebuild ({', '.join(sources)}) "
            f"SELECT {', '.join(sources.values())} FROM {table} "
            f"WHERE {' AND '.join(conditions) or 'TRUE'}"
        )

        # Indexes are recreated by the schema, triggers are kept as they are.
        triggers = await connection.fetch_all(
            "SELECT sql FROM sqlite_master WHERE tbl_name=:name AND type='trigger'",
            {"name": table},
        )
        sequence = await connection.fetch_val(
            "SELECT seq FROM sqlite_sequence WHERE name=:name", {"name": table}
        )
        await connection.execute(f"DROP TABLE {table}")
        await connection.execute(f"ALTER TABLE {table}_rebuild RENAME TO {table}")
        for trigger in triggers:
            await connection.execute(trigger["sql"])

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

    return rebuilt
