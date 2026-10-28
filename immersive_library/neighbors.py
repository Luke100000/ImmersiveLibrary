import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import closing

import numpy as np
from loguru import logger
from scipy import sparse

from immersive_library.database import Connection, database
from immersive_library.services.recommendations import (
    COLLECTION_WEIGHT,
    RECENT_ITEM_LIMIT,
)

# Damps pairs with few shared users: one counts at 1/6 strength, five at half.
DAMPING = 5

# Pairs with less evidence are mostly chance overlaps of users who like a lot, so
# they are not kept.
MIN_SHARED = 3
MIN_SCORE = 0.08
NEIGHBORS = 50

# Assets per product chunk and write transaction, keeping memory and lock times low.
CHUNK_SIZE = 1000

OWNERSHIP = f"""
    SELECT 'user ' || user_id, content_id, 1.0 FROM (
        SELECT likes.user_id, likes.content_id, ROW_NUMBER() OVER (
            PARTITION BY likes.user_id ORDER BY likes.created_at DESC
        ) AS position
        FROM likes JOIN content ON content.oid = likes.content_id AND content.project = :project
    ) WHERE position <= {RECENT_ITEM_LIMIT}
    UNION ALL
    -- A user's collections weight grows only logarithmically
    SELECT 'collection ' || collection_id, content_id,
           {COLLECTION_WEIGHT} * ln(owned + 5) / ln(6) / owned
    FROM (
        SELECT items.collection_id, items.content_id, ROW_NUMBER() OVER (
            PARTITION BY items.collection_id ORDER BY items.created_at DESC
        ) AS position, (
            SELECT count(*) FROM collections AS owned_collections
            WHERE owned_collections.user_id = collections.user_id
                AND owned_collections.project = :project
        ) AS owned
        FROM collection_items AS items
        JOIN collections ON collections.oid = items.collection_id
            AND collections.project = :project
    ) WHERE position <= {RECENT_ITEM_LIMIT}
"""


def project_neighbors(
    connection: sqlite3.Connection, project: str
) -> Iterator[tuple[list[int], list[tuple[int, int, float]]]]:
    """
    Item-to-item collaborative filtering: two assets are similar when the same users
    like them or the same collections contain them. Yields chunks of content IDs with
    their top neighbors as (content_id, neighbor_id, score) rows.
    """
    rows = connection.execute(OWNERSHIP, {"project": project}).fetchall()
    if not rows:
        return

    owners, items, weights = zip(*rows)
    _, owner_index = np.unique(owners, return_inverse=True)
    content_ids, item_index = np.unique(items, return_inverse=True)

    # Square roots, so that a shared owner adds its weight to the overlap.
    matrix = sparse.csr_matrix(
        (np.sqrt(np.array(weights, dtype=np.float32)), (owner_index, item_index))
    )
    sizes = np.asarray(matrix.multiply(matrix).sum(axis=0)).ravel()
    transposed = matrix.T.tocsr()

    for start in range(0, len(content_ids), CHUNK_SIZE):
        overlap = (transposed[start : start + CHUNK_SIZE] @ matrix).tocoo()
        row, column, shared = overlap.row, overlap.col, overlap.data
        kept = (row + start != column) & (shared >= MIN_SHARED)
        row, column, shared = row[kept], column[kept], shared[kept]

        # Cosine similarity, damped for few shared owners.
        score = shared / np.sqrt(sizes[row + start] * sizes[column])
        score *= shared / (shared + DAMPING)
        strong = score >= MIN_SCORE
        row, column, score = row[strong], column[strong], score[strong]

        order = np.lexsort((-score, row))
        row, column, score = row[order], column[order], score[order]
        rank = np.arange(len(row)) - np.searchsorted(row, row)
        top = rank < NEIGHBORS
        neighbors = zip(
            content_ids[row[top] + start].tolist(),
            content_ids[column[top]].tolist(),
            score[top].tolist(),
        )
        yield content_ids[start : start + CHUNK_SIZE].tolist(), list(neighbors)


def compute_neighbors() -> None:
    with closing(
        sqlite3.connect(database.url.database, factory=Connection)
    ) as connection:
        connection.execute(
            "CREATE TEMP TABLE computed (content_id INTEGER PRIMARY KEY)"
        )
        projects = connection.execute("SELECT DISTINCT project FROM content").fetchall()
        for (project,) in projects:
            start = time.monotonic()
            for content_ids, neighbors in project_neighbors(connection, project):
                with connection:
                    connection.execute(
                        "DELETE FROM content_neighbors "
                        "WHERE content_id IN (SELECT value FROM json_each(?))",
                        (json.dumps(content_ids),),
                    )
                    connection.executemany(
                        "INSERT INTO content_neighbors VALUES (?, ?, ?)", neighbors
                    )
                    connection.executemany(
                        "INSERT INTO computed VALUES (?)", ((i,) for i in content_ids)
                    )
            logger.info(
                "Computed {} neighbors in {:.1f} s", project, time.monotonic() - start
            )

        with connection:
            connection.execute(
                "DELETE FROM content_neighbors "
                "WHERE content_id NOT IN (SELECT content_id FROM computed)"
            )


if __name__ == "__main__":
    compute_neighbors()
