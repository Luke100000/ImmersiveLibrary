import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from immersive_library.services.recommendations import RANK_SMOOTHING
from immersive_library.services.reports import REPORT_SCORE

# bm25 weights of the title, tags, username and description columns.
KEYWORD_COLUMNS = "4.0, 3.0, 2.0, 1.0"
COLLECTION_KEYWORD_COLUMNS = "4.0, 2.0, 1.0"

# All words in what uploaders wrote, or all of them in the description.
STRICT_QUERY = "({{title tags username}} : ({words})) OR (description : ({words}))"

RANKING_JOINS = "\n JOIN keyword_rank ON keyword_rank.content_id = c.oid"

COLLECTION_CONTENT_VISIBILITY = f"""
    c.project=:project AND NOT author.banned AND {REPORT_SCORE} <= 1
    AND NOT EXISTS (
        SELECT 1 FROM reports WHERE reports.content_id=c.oid
            AND reports.user_id=:viewer_id AND reports.reason='DEFAULT'
    )
"""


@dataclass
class SearchPlan:
    conditions: list[str] = field(default_factory=list)
    values: dict[str, str] = field(default_factory=dict)
    ranking: str | None = None


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def prefix_query(words: list[str], operator: str = " ") -> str:
    """An FTS5 query matching the words as word prefixes."""
    return operator.join(f'"{word}"*' for word in words)


def keyword_query(term_words: list[str], rank: bool, title_only: bool) -> str:
    if title_only:
        return f"title : ({prefix_query(term_words)})"
    return prefix_query(term_words, " OR " if rank else " ")


def keyword_condition(parameter: str) -> str:
    return f"c.oid IN (SELECT rowid FROM content_search WHERE content_search MATCH :{parameter})"


def query_terms(q: str | None) -> Iterator[tuple[str, str, bool]]:
    terms = [term.strip() for term in (q or "").split(",") if term.strip()]
    for index, term in enumerate(terms):
        negated = term.startswith("-")
        yield f"term_{index}", term[1:].strip() if negated else term, negated


def plan_search(q: str | None, rank: bool) -> SearchPlan:
    plan = SearchPlan()
    ranking_queries = []
    for parameter, search_term, negated in query_terms(q):
        if search_term.startswith("@"):
            condition = f"username = :{parameter}"
            plan.values[parameter] = search_term[1:].strip()
        elif search_term.startswith("#"):
            condition = f"""EXISTS (
                    SELECT 1 FROM tags
                    WHERE tags.content_id = c.oid AND tags.tag = :{parameter}
                )"""
            plan.values[parameter] = search_term[1:].strip()
        elif term_words := words(search_term):
            title_only = search_term.startswith("~")
            ranked = rank and not negated
            query = keyword_query(term_words, ranked, title_only)
            condition = keyword_condition(parameter)
            if ranked or title_only:
                plan.values[parameter] = query
            else:
                plan.values[parameter] = STRICT_QUERY.format(words=query)
            if ranked:
                ranking_queries.append(f"({query})")
        else:
            condition = "0"

        plan.conditions.append(f"{'NOT ' if negated else ''}{condition}")

    if ranking_queries:
        plan.values["ranking_keywords"] = " OR ".join(ranking_queries)
        plan.ranking = f"""
            keyword_rank AS (
                SELECT rowid AS content_id, ROW_NUMBER() OVER (
                    ORDER BY bm25(content_search, {KEYWORD_COLUMNS}), rowid
                ) AS rank
                FROM content_search WHERE content_search MATCH :ranking_keywords
            )
        """

    return plan


def collection_content_condition(condition: str) -> str:
    """Maps matching, visible assets to collections without copying their text."""
    return f"""collections.oid IN (
        SELECT collection_items.collection_id FROM content c
        JOIN collection_items ON collection_items.content_id=c.oid
        JOIN users AS author ON author.oid=c.user_id
        JOIN precomputation ON precomputation.content_id=c.oid
        WHERE {COLLECTION_CONTENT_VISIBILITY} AND {condition}
    )"""


def collection_keyword_ranking(parameter: str, title_only: bool) -> str:
    """Ranks metadata and each collection's best asset separately before fusion."""
    metadata_hits = f"{parameter}_metadata_hits"
    asset_hits = f"{parameter}_asset_hits"
    matches = f"{parameter}_matches"
    sources = f"""
        SELECT collections.oid AS collection_id, 0 AS source, hits.score
        FROM {metadata_hits} hits
        JOIN collections ON collections.oid=hits.rowid
        WHERE collections.project=:project
            AND (collections.user_id=:viewer_id OR collections.is_public=1)
    """
    ctes = [
        f"""{metadata_hits} AS MATERIALIZED (
            SELECT rowid, bm25(collection_search, {COLLECTION_KEYWORD_COLUMNS}) AS score
            FROM collection_search WHERE collection_search MATCH :{parameter}
        )"""
    ]
    if not title_only:
        ctes.append(f"""{asset_hits} AS MATERIALIZED (
            SELECT rowid, bm25(content_search, {KEYWORD_COLUMNS}) AS score
            FROM content_search WHERE content_search MATCH :{parameter}_content
        )""")
        sources += f"""
            UNION ALL
            SELECT collection_items.collection_id, 1 AS source, MIN(hits.score)
            FROM {asset_hits} hits
            JOIN content c ON c.oid=hits.rowid
            JOIN collection_items ON collection_items.content_id=c.oid
            JOIN collections ON collections.oid=collection_items.collection_id
            JOIN users AS author ON author.oid=c.user_id
            JOIN precomputation ON precomputation.content_id=c.oid
            WHERE {COLLECTION_CONTENT_VISIBILITY}
                AND collections.project=:project
                AND (collections.user_id=:viewer_id OR collections.is_public=1)
            GROUP BY collection_items.collection_id
        """
    ctes.append(f"{matches} AS MATERIALIZED ({sources})")
    ctes.append(f"""{parameter}_ranks AS (
        SELECT collection_id,
               DENSE_RANK() OVER (PARTITION BY source ORDER BY score) AS rank
        FROM {matches}
    )""")
    return ", ".join(ctes)


def plan_collection_search(q: str | None, rank: bool = True) -> SearchPlan:
    plan = SearchPlan()
    rankings = []
    scores = []
    for parameter, search_term, negated in query_terms(q):
        if search_term.startswith("@"):
            condition = f"users.username = :{parameter}"
            plan.values[parameter] = search_term[1:].strip()
        elif search_term.startswith("#"):
            condition = collection_content_condition(f"""c.oid IN (
                SELECT content_id FROM tags WHERE tag=:{parameter}
            )""")
            plan.values[parameter] = search_term[1:].strip()
        elif term_words := words(search_term):
            title_only = search_term.startswith("~")
            ranked = rank and not negated
            query = keyword_query(term_words, ranked, title_only)
            plan.values[parameter] = query
            if not title_only:
                content_parameter = f"{parameter}_content"
                plan.values[content_parameter] = (
                    query if ranked else STRICT_QUERY.format(words=query)
                )

            if not ranked:
                condition = f"""collections.oid IN (
                    SELECT rowid FROM collection_search
                    WHERE collection_search MATCH :{parameter}
                )"""
                if not title_only:
                    content_condition = collection_content_condition(
                        keyword_condition(f"{parameter}_content")
                    )
                    condition = f"({condition} OR {content_condition})"
            else:
                rankings.append(collection_keyword_ranking(parameter, title_only))
                scores.append(f"""SELECT collection_id,
                    1.0 / ({RANK_SMOOTHING} + rank) AS score FROM {parameter}_ranks""")
                condition = f"collections.oid IN (SELECT collection_id FROM {parameter}_matches)"
        else:
            condition = "0"

        plan.conditions.append(f"{'NOT ' if negated else ''}{condition}")

    if rankings:
        rankings.append(f"""collection_keyword_rank AS (
            SELECT collection_id, SUM(score) AS score FROM (
                {" UNION ALL ".join(scores)}
            ) GROUP BY collection_id
        )""")
        plan.ranking = ", ".join(rankings)

    return plan
