from databases import Database


async def migrate_user_tokens(database: Database) -> None:
    async with database.connection() as connection:
        await connection.execute("BEGIN IMMEDIATE")
        try:
            columns = await connection.fetch_all("PRAGMA table_info(users)")
            if any(column["name"] == "token" for column in columns):
                await connection.execute("""
                    INSERT OR IGNORE INTO user_tokens (token, user_id)
                    SELECT token, oid
                    FROM users
                    WHERE token IS NOT NULL AND token != ''
                """)
                await connection.execute("DROP INDEX IF EXISTS users_token")
                await connection.execute("ALTER TABLE users DROP COLUMN token")
        except BaseException:
            await connection.execute("ROLLBACK")
            raise
        else:
            await connection.execute("COMMIT")
