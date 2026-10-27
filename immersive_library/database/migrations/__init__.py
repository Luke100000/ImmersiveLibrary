from databases import Database

from immersive_library.database.migrations.content_cascades import (
    migrate_content_cascades,
)
from immersive_library.database.migrations.timestamps import migrate_timestamps
from immersive_library.database.migrations.unique_constraints import (
    migrate_unique_constraints,
)
from immersive_library.database.migrations.user_tokens import migrate_user_tokens


async def run_migrations(database: Database) -> None:
    await migrate_user_tokens(database)
    await migrate_unique_constraints(database)
    await migrate_content_cascades(database)
    await migrate_timestamps(database)
