"""Estimates created_at for rows that predate timestamp tracking.

Every backup (named DDMMYY.db) anchors the newest row that existed on its date, the live
database anchors its newest untimestamped row to now, and rows in between are interpolated
linearly by rowid. Rows older than the first backup get the first backup's date.
Only rows still at LEGACY_TIMESTAMP are touched, so running it twice changes nothing.

The backups are read locally and the result is plain SQL, so the live database can be remote:
    uv run scripts/backfill_timestamps.py                          # applies to data/database.db
    uv run scripts/backfill_timestamps.py --print | ssh prod "sqlite3 -bail /path/database.db"
"""

import argparse
import datetime
import itertools
import sqlite3
import sys
from pathlib import Path

LEGACY_TIMESTAMP = 0

# Natural keys identify rows across backups whose rowids were renumbered.
KEYS = {
    "users": ("oid",),
    "content": ("oid",),
    "likes": ("user_id", "content_id"),
    "reports": ("user_id", "content_id", "reason"),
    "tags": ("content_id", "tag"),
}
LEGACY_NAMES = {"user_id": "userid", "content_id": "contentid"}
SAMPLES = 100


def snapshot_time(path: Path) -> int | None:
    try:
        date = datetime.datetime.strptime(path.stem, "%d%m%y")
    except ValueError:
        return None
    # The time of day is unknown, noon halves the worst case error.
    return int(date.replace(hour=12, tzinfo=datetime.UTC).timestamp())


def open_backup(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)


def key_columns(db: sqlite3.Connection, table: str) -> list[str] | None:
    columns = {row[1] for row in db.execute(f'PRAGMA table_info("{table}")')}
    if not columns:
        return None
    return [name if name in columns else LEGACY_NAMES[name] for name in KEYS[table]]


def select_keys(columns: list[str], table: str) -> str:
    return f"SELECT rowid, {', '.join(columns)} FROM {table}"


def normalize(row: tuple) -> tuple:
    # Old backups store some ids as text.
    return tuple(None if value is None else str(value) for value in row)


def quote(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return str(value)


def same_numbering(db, columns, reference, reference_columns, table) -> bool:
    sample = db.execute(
        f"{select_keys(columns, table)} ORDER BY random() LIMIT {SAMPLES}"
    ).fetchall()
    found = {
        row[0]: row[1:]
        for row in reference.execute(
            f"{select_keys(reference_columns, table)} WHERE rowid IN "
            f"({', '.join(str(row[0]) for row in sample) or 'NULL'})"
        )
    }
    matches = sum(
        row[0] in found and normalize(found[row[0]]) == normalize(row[1:])
        for row in sample
    )
    return matches >= 0.9 * len(found) > 0


def survivor_anchor(db, columns, reference, reference_columns, table) -> int | None:
    # Rows that existed in the backup form a prefix of the reference, minus deletions.
    keys = {normalize(row[1:]) for row in db.execute(select_keys(columns, table))}
    survivors = sum(
        normalize(row[1:]) in keys
        for row in reference.execute(select_keys(reference_columns, table))
    )
    if survivors == 0:
        return None
    return reference.execute(
        f"SELECT rowid FROM {table} ORDER BY rowid LIMIT 1 OFFSET {survivors - 1}"
    ).fetchone()[0]


def find_anchors(table, backups, reference) -> list[tuple[int, int]]:
    reference_columns = key_columns(reference, table)
    anchors = []
    for time, path in backups:
        db = open_backup(path)
        columns = key_columns(db, table)
        if columns is None:
            continue

        max_id = db.execute(f"SELECT MAX(rowid) FROM {table}").fetchone()[0]
        if max_id is None:
            continue
        if same_numbering(db, columns, reference, reference_columns, table):
            sequence = db.execute(
                "SELECT seq FROM sqlite_sequence WHERE name=?", (table,)
            ).fetchone()
            anchor = max(max_id, sequence[0] if sequence else 0)
        else:
            anchor = survivor_anchor(db, columns, reference, reference_columns, table)
            print(
                f"{table}: {path.name} renumbered, anchored at {anchor}",
                file=sys.stderr,
            )

        # Keep ids strictly increasing over time.
        if anchor is not None and (not anchors or anchor > anchors[-1][0]):
            anchors.append((anchor, time))
    return anchors


def guard_statement(table, reference) -> str:
    # Abort if the live rowids do not match the reference backup's numbering.
    columns = key_columns(reference, table)
    # Backups may hold orphans of deleted content, which live databases no longer have.
    orphans = (
        f"WHERE {columns[KEYS[table].index('content_id')]} IN (SELECT oid FROM content)"
        if "content_id" in KEYS[table]
        else ""
    )
    sample = reference.execute(
        f"{select_keys(columns, table)} {orphans} ORDER BY random() LIMIT {SAMPLES}"
    ).fetchall()
    values = ", ".join(f"({', '.join(map(quote, row))})" for row in sample)
    conditions = " AND ".join(
        f"{table}.{name} IS sample.column{i + 2}" for i, name in enumerate(KEYS[table])
    )
    return (
        f"INSERT INTO backfill_guard SELECT COUNT(*) >= {int(0.9 * len(sample))} "
        f"FROM (VALUES {values}) AS sample "
        f"JOIN {table} ON {table}.rowid = sample.column1 AND {conditions}"
    )


def table_statements(table, anchors, reference) -> list[str]:
    legacy = f"created_at = {LEGACY_TIMESTAMP}"
    first_id, first_time = anchors[0]
    last_id, last_time = anchors[-1]
    statements = [
        guard_statement(table, reference),
        # The live state anchors the last batch, which is in no backup.
        (
            f"CREATE TEMP TABLE backfill_{table} AS "
            f"SELECT MAX(rowid) AS id, unixepoch() AS time FROM {table} WHERE {legacy}"
        ),
        (
            f"UPDATE {table} SET created_at = {first_time} "
            f"WHERE {legacy} AND rowid <= {first_id}"
        ),
    ]
    for (start_id, start_time), (end_id, end_time) in itertools.pairwise(anchors):
        rate = (end_time - start_time) / (end_id - start_id)
        statements.append(
            f"UPDATE {table} SET created_at = "
            f"CAST({start_time} + (rowid - {start_id}) * {rate!r} AS INTEGER) "
            f"WHERE {legacy} AND rowid > {start_id} AND rowid <= {end_id}"
        )
    statements.append(
        f"UPDATE {table} SET created_at = CAST({last_time} + (rowid - {last_id}) "
        f"* ((SELECT time FROM backfill_{table}) - {last_time}) * 1.0 "
        f"/ ((SELECT id FROM backfill_{table}) - {last_id}) AS INTEGER) "
        f"WHERE {legacy} AND rowid > {last_id}"
    )
    return statements


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", type=Path, default=Path("data/database.db"))
    parser.add_argument("--backups", type=Path, default=Path("data/backup"))
    parser.add_argument(
        "--print", action="store_true", help="print the SQL instead of applying it"
    )
    args = parser.parse_args()

    backups = sorted(
        (time, path)
        for path in args.backups.glob("*.db")
        if (time := snapshot_time(path)) is not None
    )
    reference = open_backup(backups[-1][1])

    statements = {}
    for table in KEYS:
        anchors = find_anchors(table, backups, reference)
        print(f"{table}: {len(anchors)} anchors", file=sys.stderr)
        statements[table] = table_statements(table, anchors, reference)
    statements["content updated_at"] = [
        (
            f"UPDATE content SET updated_at = created_at "
            f"WHERE updated_at = {LEGACY_TIMESTAMP}"
        )
    ]

    setup = "CREATE TEMP TABLE backfill_guard (ok INTEGER CHECK (ok))"
    if args.print:
        print("BEGIN IMMEDIATE;")
        print(f"{setup};")
        for table_statements_ in statements.values():
            for statement in table_statements_:
                print(f"{statement};")
        print("COMMIT;")
        return

    live = sqlite3.connect(args.live, isolation_level=None)
    live.execute("BEGIN IMMEDIATE")
    try:
        live.execute(setup)
        for table, table_statements_ in statements.items():
            changed = 0
            for statement in table_statements_:
                cursor = live.execute(statement)
                if statement.startswith("UPDATE"):
                    changed += cursor.rowcount
            print(f"{table}: {changed} rows updated", file=sys.stderr)
    except BaseException:
        live.execute("ROLLBACK")
        raise
    live.execute("COMMIT")


if __name__ == "__main__":
    main()
