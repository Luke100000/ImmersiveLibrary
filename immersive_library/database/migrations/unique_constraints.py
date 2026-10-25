from databases import Database


async def migrate_unique_constraints(database: Database) -> None:
    async with database.connection() as connection:
        await connection.execute("BEGIN IMMEDIATE")
        try:
            for table, columns in (
                ("likes", "user_id, content_id"),
                ("reports", "user_id, content_id, reason"),
                ("tags", "content_id, tag"),
            ):
                index_name = f"{table}_unique"
                if await connection.fetch_val(
                    "SELECT 1 FROM sqlite_master WHERE type='index' AND name=:name",
                    {"name": index_name},
                ):
                    continue

                # TODO: Temporary cleanup for old databases
                await connection.execute(
                    f"DELETE FROM {table} WHERE rowid NOT IN (SELECT MIN(rowid) FROM {table} GROUP BY {columns})"
                )
                await connection.execute(
                    f"CREATE UNIQUE INDEX {index_name} ON {table} ({columns})"
                )
            await connection.execute("COMMIT")
        except BaseException:
            await connection.execute("ROLLBACK")
            raise
