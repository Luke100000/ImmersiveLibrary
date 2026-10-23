from databases import Database


async def migrate_unique_constraints(database: Database):
    async with database.connection() as connection:
        await connection.execute("BEGIN IMMEDIATE")
        try:
            for table, columns in (
                ("likes", "userid, contentid"),
                ("reports", "userid, contentid, reason"),
                ("tags", "contentid, tag"),
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


async def migrate_content_cascades(database: Database):
    async with database.connection() as connection:
        await connection.execute("BEGIN IMMEDIATE")
        try:
            for table in ("likes", "reports", "tags", "precomputation"):
                # Refresh SQLite's schema cache after waiting for another worker.
                schema = await connection.fetch_val(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name=:name",
                    {"name": table},
                )
                foreign_keys = await connection.fetch_all(
                    f"PRAGMA foreign_key_list({table})"
                )
                if any(
                    key["from"] == "contentid"
                    and key["table"] == "content"
                    and key["to"] == "oid"
                    and key["on_delete"] == "CASCADE"
                    for key in foreign_keys
                ):
                    continue

                definition, suffix = schema.split("(", 1)[1].rsplit(")", 1)
                await connection.execute(
                    f"CREATE TABLE {table}_cascade ({definition}, "
                    f"FOREIGN KEY(contentid) REFERENCES content(oid) ON DELETE CASCADE){suffix}"
                )

                # Preserve rowids, indexes and triggers when rebuilding the child tables.
                columns = ", ".join(
                    f'"{column["name"]}"'
                    for column in await connection.fetch_all(
                        f"PRAGMA table_info({table})"
                    )
                )
                if table != "precomputation":
                    columns = f"rowid, {columns}"

                await connection.execute(
                    f"INSERT INTO {table}_cascade ({columns}) "
                    f"SELECT {columns} FROM {table} "
                    "WHERE contentid IS NULL OR contentid IN (SELECT oid FROM content)"
                )
                objects = await connection.fetch_all(
                    "SELECT sql FROM sqlite_master WHERE tbl_name=:name "
                    "AND type IN ('index', 'trigger') AND sql IS NOT NULL",
                    {"name": table},
                )
                await connection.execute(f"DROP TABLE {table}")
                await connection.execute(
                    f"ALTER TABLE {table}_cascade RENAME TO {table}"
                )
                for obj in objects:
                    await connection.execute(obj["sql"])

                if await connection.fetch_all(f"PRAGMA foreign_key_check({table})"):
                    raise RuntimeError(
                        f"Foreign key check failed after migrating {table}"
                    )
        except BaseException:
            await connection.execute("ROLLBACK")
            raise
        else:
            await connection.execute("COMMIT")
