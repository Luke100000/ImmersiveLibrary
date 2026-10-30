import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import closing

import numpy as np
from loguru import logger
from usearch.index import Index

from immersive_library.database import Connection, database
from immersive_library.services.embeddings import DIMENSIONS

NEIGHBORS = 30

# A new asset is added to the lists of this many of its nearest assets.
CANDIDATES = 100

# Vectors per read and lists per write. Short reads never lock the database.
CHUNK_SIZE = 4096

# Assets checked against an exact search after each rebuild.
RECALL_SAMPLE = 200

VECTORS = """
    SELECT e.content_id, e.vector FROM content_embeddings AS e
    JOIN content ON content.oid = e.content_id
    WHERE content.project = ? AND e.vector IS NOT NULL AND e.content_id > ?
    ORDER BY e.content_id LIMIT ?
"""


def vector_chunks(
    connection: sqlite3.Connection, project: str
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    last_id = -1
    while rows := connection.execute(
        VECTORS, (project, last_id, CHUNK_SIZE)
    ).fetchall():
        ids = np.array([row[0] for row in rows], dtype=np.int64)
        vectors = np.frombuffer(b"".join(row[1] for row in rows), dtype=np.int8)
        yield ids, vectors.reshape(len(rows), DIMENSIONS)
        last_id = rows[-1][0]


def normalized(vectors: np.ndarray) -> np.ndarray:
    values = vectors.astype(np.float32)
    return values / np.linalg.norm(values, axis=1, keepdims=True)


def exact_nearest(
    connection: sqlite3.Connection, project: str, queries: np.ndarray, k: int
) -> tuple[np.ndarray, np.ndarray]:
    """The exact k nearest assets per query, the query itself included."""
    queries = normalized(queries)
    best_ids = np.empty((len(queries), 0), dtype=np.int64)
    best_scores = np.empty((len(queries), 0), dtype=np.float32)
    for ids, vectors in vector_chunks(connection, project):
        scores = np.hstack([best_scores, queries @ normalized(vectors).T])
        candidates = np.hstack(
            [best_ids, np.broadcast_to(ids, (len(queries), len(ids)))]
        )
        top = np.argsort(-scores, axis=1)[:, :k]
        best_ids = np.take_along_axis(candidates, top, axis=1)
        best_scores = np.take_along_axis(scores, top, axis=1)
    return best_ids, best_scores


def build_index(connection: sqlite3.Connection, project: str) -> Index:
    """Holds the only in-memory copy of the vectors."""
    index = Index(ndim=DIMENSIONS, metric="cos", dtype="i8")
    for ids, vectors in vector_chunks(connection, project):
        index.add(ids, vectors)
    return index


def project_neighbors(
    connection: sqlite3.Connection, project: str, index: Index
) -> Iterator[tuple[list[int], list[tuple[int, int, float]]]]:
    """Yields content IDs with their neighbor rows, one chunk at a time."""
    for ids, vectors in vector_chunks(connection, project):
        matches = index.search(vectors, NEIGHBORS + 1)
        rows = []
        for content_id, keys, distances, count in zip(
            ids.tolist(), matches.keys, matches.distances, matches.counts
        ):
            rows += [
                (content_id, int(key), 1.0 - float(distance))
                for key, distance in zip(keys[:count], distances[:count])
                if key != content_id
            ][:NEIGHBORS]
        yield ids.tolist(), rows


def log_recall(connection: sqlite3.Connection, project: str, index: Index) -> None:
    rows = connection.execute(
        "SELECT e.vector FROM content_embeddings AS e "
        "JOIN content ON content.oid = e.content_id "
        "WHERE content.project = ? AND e.vector IS NOT NULL "
        "ORDER BY random() LIMIT ?",
        (project, RECALL_SAMPLE),
    ).fetchall()
    if not rows:
        return
    queries = np.frombuffer(b"".join(row[0] for row in rows), dtype=np.int8)
    queries = queries.reshape(len(rows), DIMENSIONS)
    exact, _ = exact_nearest(connection, project, queries, NEIGHBORS + 1)
    found = index.search(queries, NEIGHBORS + 1).keys
    shared = [len(set(e) & set(f)) for e, f in zip(exact, found)]
    recall = np.mean(shared) / (NEIGHBORS + 1)
    logger.info("Image neighbor recall for {}: {:.3f}", project, recall)


def compute_image_neighbors() -> None:
    with closing(
        sqlite3.connect(database.url.database, factory=Connection)
    ) as connection:
        connection.execute(
            "CREATE TEMP TABLE computed (content_id INTEGER PRIMARY KEY)"
        )
        projects = connection.execute("SELECT DISTINCT project FROM content").fetchall()
        for (project,) in projects:
            start = time.monotonic()
            index = build_index(connection, project)
            if not len(index):
                continue
            for content_ids, neighbors in project_neighbors(connection, project, index):
                with connection:
                    connection.execute(
                        "DELETE FROM content_image_neighbors "
                        "WHERE content_id IN (SELECT value FROM json_each(?))",
                        (json.dumps(content_ids),),
                    )
                    connection.executemany(
                        "INSERT INTO content_image_neighbors VALUES (?, ?, ?)",
                        neighbors,
                    )
                    connection.executemany(
                        "INSERT INTO computed VALUES (?)", ((i,) for i in content_ids)
                    )
            logger.info(
                "Computed {} image neighbors of {} assets in {:.1f} s",
                project,
                len(index),
                time.monotonic() - start,
            )
            log_recall(connection, project, index)

        with connection:
            connection.execute(
                "DELETE FROM content_image_neighbors "
                "WHERE content_id NOT IN (SELECT content_id FROM computed)"
            )


def add_image_neighbors(content_id: int) -> None:
    """Lists a newly embedded asset's neighbours and adds it to theirs."""
    with closing(
        sqlite3.connect(database.url.database, factory=Connection)
    ) as connection:
        row = connection.execute(
            "SELECT content.project, e.vector FROM content_embeddings AS e "
            "JOIN content ON content.oid = e.content_id "
            "WHERE e.content_id = ? AND e.vector IS NOT NULL",
            (content_id,),
        ).fetchone()
        if row is None:
            return
        project, vector = row
        query = np.frombuffer(vector, dtype=np.int8).reshape(1, DIMENSIONS)
        ids, scores = exact_nearest(connection, project, query, CANDIDATES + 1)
        candidates = [
            (int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i != content_id
        ]

        with connection:
            connection.execute(
                "DELETE FROM content_image_neighbors WHERE content_id = ?",
                (content_id,),
            )
            connection.executemany(
                "INSERT INTO content_image_neighbors VALUES (?, ?, ?)",
                ((content_id, i, s) for i, s in candidates[:NEIGHBORS]),
            )
            connection.executemany(
                "INSERT OR REPLACE INTO content_image_neighbors VALUES (?, ?, ?)",
                ((i, content_id, s) for i, s in candidates),
            )
            # Trims the lists it was added to.
            connection.execute(
                f"""
                DELETE FROM content_image_neighbors
                WHERE (content_id, neighbor_id) IN (
                    SELECT content_id, neighbor_id FROM (
                        SELECT content_id, neighbor_id, ROW_NUMBER() OVER (
                            PARTITION BY content_id ORDER BY score DESC
                        ) AS position
                        FROM content_image_neighbors
                        WHERE content_id IN (SELECT value FROM json_each(?))
                    ) WHERE position > {NEIGHBORS}
                )
                """,
                (json.dumps([i for i, _ in candidates]),),
            )


if __name__ == "__main__":
    compute_image_neighbors()
