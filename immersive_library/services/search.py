import re
from dataclasses import dataclass, field

# bm25 weights of the title, tags and username columns.
KEYWORD_COLUMNS = "4.0, 3.0, 2.0"

RANKING_JOINS = "\n JOIN keyword_rank ON keyword_rank.content_id = c.oid"


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


def keyword_condition(parameter: str) -> str:
    return f"c.oid IN (SELECT rowid FROM content_search WHERE content_search MATCH :{parameter})"


def plan_search(q: str | None, rank: bool) -> SearchPlan:
    plan = SearchPlan()
    terms = [term.strip() for term in (q or "").split(",") if term.strip()]
    for index, term in enumerate(terms):
        parameter = f"term_{index}"
        negated = term.startswith("-")
        search_term = term[1:].strip() if negated else term

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
            condition = keyword_condition(parameter)
            query = prefix_query(term_words)
            if search_term.startswith("~"):
                query = f"title : ({query})"
            plan.values[parameter] = query
        else:
            condition = "0"

        plan.conditions.append(f"{'NOT ' if negated else ''}{condition}")

    # Every positive term ranks. Each contributes words that every result contains,
    # which the inner ranking join relies on.
    ranking_words = [
        word for term in terms if not term.startswith("-") for word in words(term)
    ]
    if rank and ranking_words:
        plan.values["ranking_keywords"] = prefix_query(ranking_words, " OR ")
        plan.ranking = f"""
            keyword_rank AS (
                SELECT rowid AS content_id, ROW_NUMBER() OVER (
                    ORDER BY bm25(content_search, {KEYWORD_COLUMNS}), rowid
                ) AS rank
                FROM content_search WHERE content_search MATCH :ranking_keywords
            )
        """

    return plan
