from immersive_library.database import database
from immersive_library.enums import SitemapSection
from immersive_library.services.reports import REPORT_SCORE

# Search engines accept up to 50,000 URLs per sitemap.
PAGE_SIZE = 10_000

# Keeps unvetted or possibly illegal content out of search engines: indexed content
# needs some likes, an author who is not banned, and next to no open reports. Popular
# content tolerates a stray report, about one per hundred likes.
MIN_INDEXED_LIKES = 5
MAX_INDEXED_REPORT_SCORE = 0.1
INDEXABLE_CONTENT = f"""
    FROM content AS c
    JOIN users ON users.oid = c.user_id
    JOIN precomputation ON precomputation.content_id = c.oid
    WHERE c.project = :project AND NOT users.banned
        AND precomputation.likes >= {MIN_INDEXED_LIKES}
        AND {REPORT_SCORE} <= {MAX_INDEXED_REPORT_SCORE}
"""

QUERIES = {
    SitemapSection.CONTENT: f"""
        SELECT c.oid AS id, c.updated_at {INDEXABLE_CONTENT}
        ORDER BY c.oid
    """,
    SitemapSection.COLLECTIONS: """
        SELECT oid AS id, updated_at FROM collections
        WHERE project = :project AND is_public = 1
            AND EXISTS (SELECT 1 FROM collection_items WHERE collection_id = collections.oid)
        ORDER BY oid
    """,
}


async def is_indexable(project: str, content_id: int) -> bool:
    return bool(
        await database.fetch_val(
            f"SELECT EXISTS (SELECT 1 {INDEXABLE_CONTENT} AND c.oid = :content_id)",
            {"project": project, "content_id": content_id},
        )
    )


async def page_count(project: str, section: SitemapSection) -> int:
    count = await database.fetch_val(
        f"SELECT count(*) FROM ({QUERIES[section]})", {"project": project}
    )
    return -(-count // PAGE_SIZE)


async def entries(
    project: str, section: SitemapSection, page: int
) -> list[tuple[int, int]]:
    """Ids and last modification timestamps of one sitemap page."""
    rows = await database.fetch_all(
        f"{QUERIES[section]} LIMIT :limit OFFSET :offset",
        {"project": project, "limit": PAGE_SIZE, "offset": page * PAGE_SIZE},
    )
    return [(row["id"], row["updated_at"]) for row in rows]
