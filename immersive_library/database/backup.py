import os
import sqlite3
import time
from contextlib import closing
from datetime import date
from pathlib import Path

from loguru import logger

DATABASE_PATH = Path(
    os.getenv("DATABASE_URL", "sqlite:///data/database.db").removeprefix("sqlite:///")
)
BACKUP_DIRECTORY = DATABASE_PATH.parent / "backup"
BACKUP_PREFIX = "database-"
KEEP_BACKUPS = 5


def create_backup(target: Path) -> None:
    # VACUUM INTO writes a consistent, compacted snapshot while the app keeps running.
    # Writing to a temporary file first ensures a backup is either complete or absent.
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.unlink(missing_ok=True)
    try:
        # Read-only, so a missing database fails instead of backing up a new empty one.
        source = DATABASE_PATH.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(source, uri=True, timeout=60)) as connection:
            connection.execute("VACUUM INTO ?", (str(temporary),))
        with closing(sqlite3.connect(temporary)) as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()[0]
            tables = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
        if result != "ok" or not tables:
            raise RuntimeError(f"Backup failed verification: {result}, {tables} tables")

        # VACUUM INTO does not sync its output, so persist it before it counts.
        with open(temporary, "rb") as file:
            os.fsync(file.fileno())
        temporary.rename(target)
    finally:
        temporary.unlink(missing_ok=True)


def prune_backups() -> None:
    # Only touches backups named by this module, manual backups are kept.
    backups = sorted(BACKUP_DIRECTORY.glob(f"{BACKUP_PREFIX}*.db"))
    for backup in backups[:-KEEP_BACKUPS]:
        backup.unlink()
        logger.info(f"Removed old backup {backup.name}")


def create_daily_backup() -> None:
    # ISO dates sort chronologically, which pruning relies on.
    target = BACKUP_DIRECTORY / f"{BACKUP_PREFIX}{date.today().isoformat()}.db"
    if target.exists():
        return
    start = time.monotonic()
    create_backup(target)
    logger.info(f"Created backup {target.name} in {time.monotonic() - start:.1f} s")
    prune_backups()
