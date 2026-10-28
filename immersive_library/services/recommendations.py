from dataclasses import dataclass

from databases import Database

from immersive_library.database import database
from immersive_library.utils import DAY, RECENT_DAYS

# Users and collections are described by this many of their most recent items.
RECENT_ITEM_LIMIT = 200

# A collection counts like this many users liking all its members.
COLLECTION_WEIGHT = 3

# Trust in a preference grows as seeds / (seeds + this): half at this many seeds.
PREFERENCE_PRIOR = 5

HOT_SCORE = f"""precomputation.recent_likes
    / ((unixepoch() - c.created_at) / {DAY}.0 + {RECENT_DAYS})"""

# A pseudo-random number in [0, 1) per asset and :seed.
SEEDED_RANDOM = """ABS(
    ((:seed + c.oid) * 1103515245 + 12345)
    - 2147483648 * CAST(((:seed + c.oid) * 1103515245 + 12345) / 2147483648 AS INTEGER)
) / 2147483647.0"""


@dataclass(frozen=True)
class Weights:
    """How much each signal counts in the recommended order. Internal knobs."""

    match: float
    quality: float
    personal: float
    exploration: float


BROWSE_WEIGHTS = Weights(match=0.0, quality=1.0, personal=1.0, exploration=0.005)
SEARCH_WEIGHTS = Weights(match=2.0, quality=1.0, personal=0.5, exploration=0.01)
SIMILAR_WEIGHTS = Weights(match=2.0, quality=0.5, personal=0.5, exploration=0.01)

# Added to every rank so that agreeing signals outweigh a single top rank.
RANK_SMOOTHING = 10

# How much more a brand-new upload explores than old content.
FRESH_BOOST = 4


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


def neighbor_scores(name: str, seeds: str, exclude_seeds: bool) -> str:
    """CTEs scoring content by its summed neighbor scores to the seeds."""
    exclusion = (
        f"WHERE neighbors.neighbor_id NOT IN (SELECT content_id FROM {name}_seeds)"
        if exclude_seeds
        else ""
    )
    return f"""
        {name}_seeds AS ({seeds}),
        {name} AS (
            SELECT neighbors.neighbor_id AS content_id,
                   SUM({name}_seeds.weight * neighbors.score) AS score
            FROM {name}_seeds
            JOIN content_neighbors AS neighbors
                ON neighbors.content_id = {name}_seeds.content_id
            {exclusion}
            GROUP BY neighbors.neighbor_id
        )"""


SIMILAR_RANK = """
    similar_rank AS (
        SELECT content_id, ROW_NUMBER() OVER (ORDER BY score DESC, content_id) AS rank
        FROM similar
    )"""

# Ranks the preference pool. Each further asset of an author ranks as if its score
# were divided by its position among them, so no author fills the pool.
PREFERENCE_RANK = """
    preference_rank AS (
        SELECT content_id,
               ROW_NUMBER() OVER (ORDER BY score / author_position DESC, content_id) AS rank
        FROM (
            SELECT preference.content_id, preference.score, ROW_NUMBER() OVER (
                PARTITION BY content.user_id ORDER BY preference.score DESC
            ) AS author_position
            FROM preference JOIN content ON content.oid = preference.content_id
        )
    )"""


async def refresh_quality_ranks(database: Database) -> None:
    """Ranks every asset in its project by hot, popular and all-time likes."""
    await database.execute(
        f"""
        UPDATE precomputation SET quality_rank=ranked.quality_rank
        FROM (
            -- Interleaves the three orders by each asset's best rank among them.
            SELECT content_id, ROW_NUMBER() OVER (
                PARTITION BY project ORDER BY min(hot, popular, liked), content_id
            ) AS quality_rank
            FROM (
                SELECT c.oid AS content_id, c.project,
                       ROW_NUMBER() OVER (
                           PARTITION BY c.project ORDER BY {HOT_SCORE} DESC, c.oid
                       ) AS hot,
                       ROW_NUMBER() OVER (
                           PARTITION BY c.project
                           ORDER BY precomputation.recent_likes DESC, likes DESC, c.oid
                       ) AS popular,
                       ROW_NUMBER() OVER (
                           PARTITION BY c.project ORDER BY likes DESC, c.oid
                       ) AS liked
                FROM content c JOIN precomputation ON precomputation.content_id = c.oid
            )
        ) AS ranked
        WHERE ranked.content_id = precomputation.content_id
            AND precomputation.quality_rank IS NOT ranked.quality_rank
        """
    )


async def preference_strength(project: str, user_id: int) -> float:
    """How much the user's likes say about them, approaching 1."""
    seeds = await database.fetch_val(
        f"SELECT count(*) FROM ({PREFERENCE_SEEDS})",
        {"project": project, "preference_user_id": user_id},
    )
    return seeds / (seeds + PREFERENCE_PRIOR)


def recommendation_score(keyword: bool, similar: bool, preference: float | None) -> str:
    """
    Adds up the evidence that an asset suits the request, each signal as
    weight / (rank + smoothing), plus deterministic daily randomness that explores
    new uploads most. With little evidence, exploration decides.
    """
    match_ranks = []
    weights = BROWSE_WEIGHTS
    if keyword:
        match_ranks.append("keyword_rank.rank")
        weights = SEARCH_WEIGHTS
    if similar:
        match_ranks.append("similar_rank.rank")
        weights = SIMILAR_WEIGHTS
    quality_rank = "precomputation.quality_rank"
    personal_rank = "preference_rank.rank"
    if match_ranks:
        # Global ranks would let the best assets overall crowd out the matches, so
        # the other signals are ranked among the results instead.
        quality_rank = within_results(quality_rank)
        personal_rank = within_results(personal_rank)

    signals = [(rank, weights.match / len(match_ranks)) for rank in match_ranks]
    signals.append((quality_rank, weights.quality))
    if preference:
        signals.append((personal_rank, weights.personal * preference))

    terms = [
        f"COALESCE({weight} / ({rank} + {RANK_SMOOTHING}), 0)"
        for rank, weight in signals
    ]
    freshness = (
        f"{RECENT_DAYS * DAY}.0 / (unixepoch() - c.created_at + {RECENT_DAYS * DAY})"
    )
    terms.append(
        f"{weights.exploration} * {SEEDED_RANDOM} * (1 + {FRESH_BOOST} * {freshness})"
    )
    return " + ".join(terms)


def within_results(rank: str) -> str:
    """Re-ranks assets by a rank among the listed ones, NULL where it is NULL."""
    return f"""CASE WHEN {rank} IS NOT NULL THEN ROW_NUMBER() OVER (
        PARTITION BY {rank} IS NULL ORDER BY {rank}, c.oid
    ) END"""
