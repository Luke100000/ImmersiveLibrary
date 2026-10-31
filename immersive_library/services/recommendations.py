import time
from dataclasses import dataclass

from databases import Database

from immersive_library.database import database
from immersive_library.services.reports import COLLECTION_CONTENT_VISIBILITY
from immersive_library.services.search import reciprocal_rank, within_results
from immersive_library.utils import DAY, HOUR, RECENT_DAYS

# Users and collections are described by this many of their most recent items.
RECENT_ITEM_LIMIT = 200

# A collection counts like this many users liking all its members.
COLLECTION_WEIGHT = 3

# A collection's quality is that of the assets most recently added to it.
COLLECTION_QUALITY_ITEMS = 20

# Trust in a preference grows as seeds / (seeds + this): half at this many seeds.
PREFERENCE_PRIOR = 5

# Trust in a hot score grows as recent likes / (recent likes + this)
HOT_PRIOR = 10

HOT_SCORE = f"""precomputation.recent_likes
    / ((unixepoch() - c.created_at) / {DAY}.0 + {RECENT_DAYS})
    * precomputation.recent_likes / (precomputation.recent_likes + {HOT_PRIOR}.0)"""

# A pseudo-random number in [0, 1) per item and :seed.
SEEDED_RANDOM = """ABS(
    ((:seed + {item_id}) * 1103515245 + 12345)
    - 2147483648 * CAST(((:seed + {item_id}) * 1103515245 + 12345) / 2147483648 AS INTEGER)
) / 2147483647.0"""

# How much more a brand-new upload explores than old content.
FRESH_BOOST = 4


def exploration_draw(item_id: str, created_at: str) -> str:
    """A random value per item and :seed, boosted for new items. Ranked, it explores."""
    freshness = (
        f"{RECENT_DAYS * DAY}.0 / (unixepoch() - {created_at} + {RECENT_DAYS * DAY})"
    )
    random = SEEDED_RANDOM.format(item_id=item_id)
    return f"{random} * (1 + {FRESH_BOOST} * {freshness})"


@dataclass(frozen=True)
class Weights:
    """How much each signal counts in the recommended order. Internal knobs."""

    relevance: float
    personal: float
    exploration: float


BROWSE_WEIGHTS = Weights(relevance=1.0, personal=1.5, exploration=0.5)
SEARCH_WEIGHTS = Weights(relevance=2.0, personal=1.5, exploration=0.5)

# Image shares of the blends with like-based neighbours.
SIMILAR_IMAGE_SHARE = 0.75
PREFERENCE_IMAGE_SHARE = 0.25


SIMILAR_SEEDS = """
    SELECT oid AS content_id, 1.0 AS weight FROM content WHERE oid = :similar_to
    UNION ALL
    SELECT content_id, 1.0 FROM collection_items
    WHERE collection_id = :similar_to_collection AND EXISTS (
        SELECT 1 FROM collections WHERE oid = :similar_to_collection AND project = :project
            AND (user_id = :similar_viewer_id OR is_public = 1)
    )
"""

PREFERENCE_SEEDS = f"""
    SELECT content_id, SUM(weight) AS weight FROM (
        SELECT * FROM (
            SELECT likes.content_id, 1.0 AS weight FROM likes
            JOIN content ON content.oid = likes.content_id AND content.project = :project
            WHERE likes.user_id = :preference_user_id
            ORDER BY likes.created_at DESC LIMIT {RECENT_ITEM_LIMIT}
        )
        UNION ALL
        SELECT * FROM (
            SELECT items.content_id, {COLLECTION_WEIGHT}.0 FROM collection_items AS items
            JOIN collections ON collections.oid = items.collection_id
            WHERE collections.user_id = :preference_user_id
                AND collections.project = :project
            ORDER BY items.created_at DESC LIMIT {RECENT_ITEM_LIMIT}
        )
    ) GROUP BY content_id
"""


def neighbor_scores(name: str, seeds: str, table: str, exclude_seeds: bool) -> str:
    """A CTE scoring content by its summed neighbor scores to the seeds CTE."""
    exclusion = (
        f"WHERE neighbors.neighbor_id NOT IN (SELECT content_id FROM {seeds})"
        if exclude_seeds
        else ""
    )
    return f"""
        {name} AS (
            SELECT neighbors.neighbor_id AS content_id, SUM({seeds}.weight * neighbors.score) AS score
            -- CROSS JOIN keeps the seeds first, so neighbors are looked up, not scanned.
            FROM {seeds}
            CROSS JOIN {table} AS neighbors ON neighbors.content_id = {seeds}.content_id
            {exclusion}
            GROUP BY neighbors.neighbor_id
        )"""


def weighted_rank(weight: float, scores: str) -> str:
    rank = "DENSE_RANK() OVER (ORDER BY score DESC)"
    return (
        f"SELECT content_id, {weight} * {reciprocal_rank(rank)} AS score FROM {scores}"
    )


def blended_neighbor_scores(
    name: str, seeds: str, image_share: float, exclude_seeds: bool
) -> str:
    """CTEs scoring content by its image and like-based neighbors, blended by rank."""
    images, likes = f"{name}_images", f"{name}_likes"
    return f"""
        {neighbor_scores(images, seeds, "content_image_neighbors", exclude_seeds)},
        {neighbor_scores(likes, seeds, "content_like_neighbors", exclude_seeds)},
        {name} AS (
            SELECT content_id, SUM(score) AS score FROM (
                {weighted_rank(image_share, images)}
                UNION ALL
                {weighted_rank(1 - image_share, likes)}
            )
            GROUP BY content_id
        )"""


PREFERENCE_SCORES = f"""
    preference_seeds AS ({PREFERENCE_SEEDS}),
    {blended_neighbor_scores("preference", "preference_seeds", PREFERENCE_IMAGE_SHARE, exclude_seeds=False)}"""

CONTENT_SIMILARITY_CTES = f"""
    similar_seeds AS ({SIMILAR_SEEDS}),
    {blended_neighbor_scores("similar", "similar_seeds", SIMILAR_IMAGE_SHARE, exclude_seeds=True)},
    content_similarity_rank AS (
        SELECT content_id, DENSE_RANK() OVER (ORDER BY score DESC) AS rank
        FROM similar
    )"""

# Ranks the preference pool. Each further asset of an author ranks as if its score
# were divided by its position among them, so no author fills the pool.
CONTENT_PREFERENCE_CTES = f"""
    {PREFERENCE_SCORES},
    content_preference_rank AS (
        SELECT content_id,
               ROW_NUMBER() OVER (ORDER BY score / author_position DESC, content_id) AS rank
        FROM (
            SELECT preference.content_id, preference.score, ROW_NUMBER() OVER (
                PARTITION BY content.user_id ORDER BY preference.score DESC
            ) AS author_position
            FROM preference JOIN content ON content.oid = preference.content_id
        )
    )"""


# Sums the affinity of a collection's assets over the root of its size.
COLLECTION_PREFERENCE_CTES = f"""
    {PREFERENCE_SCORES},
    collection_preference AS (
        SELECT collection_items.collection_id,
               SUM(affinity.score) / sqrt((
                   SELECT count(*) FROM collection_items AS members
                   WHERE members.collection_id = collection_items.collection_id
               )) AS score
        FROM (
            SELECT content_id, SUM(score) AS score FROM (
                SELECT content_id, score FROM preference
                UNION ALL
                SELECT content_id, weight AS score FROM preference_seeds
            ) GROUP BY content_id
        ) AS affinity
        JOIN content c ON c.oid=affinity.content_id
        JOIN collection_items ON collection_items.content_id=c.oid
        JOIN collections ON collections.oid=collection_items.collection_id
        JOIN users AS author ON author.oid=c.user_id
        JOIN precomputation ON precomputation.content_id=c.oid
        WHERE {COLLECTION_CONTENT_VISIBILITY}
            AND collections.project=:project
            AND (collections.user_id=:viewer_id OR collections.is_public=1)
            AND affinity.score > 0
        GROUP BY collection_items.collection_id
    ),
    collection_preference_rank AS (
        SELECT collection_id, DENSE_RANK() OVER (ORDER BY score DESC) AS rank
        FROM collection_preference
    )
"""


async def refresh_ranks(database: Database) -> None:
    """
    Ranks assets by hot, quality, exploration and anonymous recommendation, and
    collections by quality and exploration. Exploration is reseeded every hour.
    """
    seed = {"seed": int(time.time() / HOUR)}
    anonymous = recommendation_score(reciprocal_rank("quality"), "exploration")
    await database.execute(
        f"""
        UPDATE precomputation
        SET hot_rank=ranked.hot, quality_rank=ranked.quality,
            exploration_rank=ranked.exploration,
            recommendation_rank=ranked.recommendation
        FROM (
            SELECT content_id, hot, quality, exploration, ROW_NUMBER() OVER (
                PARTITION BY project ORDER BY {anonymous} DESC, content_id
            ) AS recommendation
            FROM (
                SELECT content_id, project, hot,
                       -- Interleaves the three orders by each asset's best rank.
                       ROW_NUMBER() OVER (
                           PARTITION BY project ORDER BY min(hot, popular, liked), content_id
                       ) AS quality,
                       ROW_NUMBER() OVER (
                           PARTITION BY project ORDER BY draw DESC, content_id
                       ) AS exploration
                FROM (
                    SELECT c.oid AS content_id, c.project,
                           ROW_NUMBER() OVER (
                               PARTITION BY c.project
                               ORDER BY {HOT_SCORE} DESC, likes DESC, c.oid
                           ) AS hot,
                           ROW_NUMBER() OVER (
                               PARTITION BY c.project
                               ORDER BY precomputation.recent_likes DESC, likes DESC, c.oid
                           ) AS popular,
                           ROW_NUMBER() OVER (
                               PARTITION BY c.project ORDER BY likes DESC, c.oid
                           ) AS liked,
                           {exploration_draw("c.oid", "c.created_at")} AS draw
                    FROM content c
                    JOIN precomputation ON precomputation.content_id = c.oid
                )
            )
        ) AS ranked
        WHERE ranked.content_id = precomputation.content_id
        """,
        seed,
    )
    await database.execute(
        f"""
        UPDATE collections
        SET quality_rank=ranked.quality, exploration_rank=ranked.exploration
        FROM (
            SELECT collections.oid AS collection_id, ROW_NUMBER() OVER (
                PARTITION BY collections.project
                ORDER BY AVG({reciprocal_rank("precomputation.quality_rank")}) DESC,
                    collections.oid
            ) AS quality, ROW_NUMBER() OVER (
                PARTITION BY collections.project
                ORDER BY {exploration_draw("collections.oid", "collections.created_at")}
                    DESC, collections.oid
            ) AS exploration
            FROM collections
            LEFT JOIN (
                SELECT collection_id, content_id, ROW_NUMBER() OVER (
                    PARTITION BY collection_id ORDER BY created_at DESC
                ) AS position
                FROM collection_items
            ) AS items
                ON items.collection_id = collections.oid
                AND items.position <= {COLLECTION_QUALITY_ITEMS}
            LEFT JOIN precomputation ON precomputation.content_id = items.content_id
            GROUP BY collections.oid
        ) AS ranked
        WHERE ranked.collection_id = collections.oid
        """,
        seed,
    )


async def preference_strength(project: str, user_id: int) -> float:
    """How much the user's likes say about them, approaching 1."""
    seeds = await database.fetch_val(
        f"SELECT count(*) FROM ({PREFERENCE_SEEDS})",
        {"project": project, "preference_user_id": user_id},
    )
    return seeds / (seeds + PREFERENCE_PRIOR)


def recommendation_score(
    relevance: str,
    exploration_rank: str,
    personal_rank: str | None = None,
    preference: float | None = None,
    searching: bool = False,
) -> str:
    weights = SEARCH_WEIGHTS if searching else BROWSE_WEIGHTS
    if searching:
        exploration_rank = within_results(exploration_rank)
    terms = [
        f"{weights.relevance} * ({relevance})",
        f"{weights.exploration} * {reciprocal_rank(exploration_rank)}",
    ]
    if personal_rank is not None and preference:
        if searching:
            personal_rank = within_results(personal_rank)
        terms.append(
            f"{weights.personal * preference} * ({reciprocal_rank(personal_rank)})"
        )
    return " + ".join(terms)
