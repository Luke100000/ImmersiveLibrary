import asyncio

from immersive_library.database import database
from immersive_library.database.schema import initialize_database
from immersive_library.utils import update_precomputation


async def prepare_database() -> None:
    await database.connect()
    try:
        await initialize_database(database)
        await update_precomputation(database)
        await database.execute("PRAGMA optimize=0x10002")
    finally:
        await database.disconnect()


if __name__ == "__main__":
    asyncio.run(prepare_database())
