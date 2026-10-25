from databases import Database


COLUMN_RENAMES = {
    "users": (("google_userid", "google_user_id"),),
    "user_tokens": (("userid", "user_id"),),
    "content": (("userid", "user_id"),),
    "reports": (("userid", "user_id"), ("contentid", "content_id")),
    "likes": (("userid", "user_id"), ("contentid", "content_id")),
    "tags": (("contentid", "content_id"),),
    "precomputation": (("contentid", "content_id"),),
}

INDEX_RENAMES = {
    "users_google_userid": "users_google_user_id",
    "user_tokens_userid": "user_tokens_user_id",
    "content_userid": "content_user_id",
    "content_project_userid": "content_project_user_id",
    "reports_userid": "reports_user_id",
    "reports_contentid": "reports_content_id",
    "likes_userid": "likes_user_id",
    "likes_contentid": "likes_content_id",
    "tags_contentid": "tags_content_id",
}


async def migrate_snake_case(database: Database) -> None:
    async with database.connection() as connection:
        await connection.execute("BEGIN IMMEDIATE")
        try:
            changed = False
            for table, renames in COLUMN_RENAMES.items():
                columns = {
                    column["name"]
                    for column in await connection.fetch_all(
                        f'PRAGMA table_info("{table}")'
                    )
                }
                for old_name, new_name in renames:
                    if old_name not in columns:
                        continue
                    if new_name in columns:
                        raise RuntimeError(
                            f"Cannot migrate {table}: both {old_name} and {new_name} exist"
                        )

                    # SQLite also updates references in indexes, triggers, views and foreign keys.
                    await connection.execute(
                        f'ALTER TABLE "{table}" RENAME COLUMN "{old_name}" TO "{new_name}"'
                    )
                    columns.remove(old_name)
                    columns.add(new_name)
                    changed = True

            for old_name, new_name in INDEX_RENAMES.items():
                index_sql = await connection.fetch_val(
                    "SELECT sql FROM sqlite_master WHERE type='index' AND name=:name",
                    {"name": old_name},
                )
                if index_sql is None:
                    continue
                if await connection.fetch_val(
                    "SELECT 1 FROM sqlite_master WHERE type='index' AND name=:name",
                    {"name": new_name},
                ):
                    raise RuntimeError(
                        f"Cannot migrate index: both {old_name} and {new_name} exist"
                    )

                # Reuse the updated definition to preserve uniqueness, expressions and predicates.
                await connection.execute(index_sql.replace(old_name, new_name, 1))
                await connection.execute(f'DROP INDEX "{old_name}"')
                changed = True

            if changed and await connection.fetch_all("PRAGMA foreign_key_check"):
                raise RuntimeError(
                    "Foreign key check failed during snake_case migration"
                )
        except BaseException:
            await connection.execute("ROLLBACK")
            raise
        else:
            await connection.execute("COMMIT")
