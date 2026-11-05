import datetime
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException
from fastapi.requests import Request
from fastapi_cache.decorator import cache as cache_result
from starlette.responses import PlainTextResponse, Response

from immersive_library.common import projects, public_url
from immersive_library.enums import SitemapSection
from immersive_library.services import sitemap as sitemap_service

router = APIRouter(tags=["Viewer"], include_in_schema=False)

# Sitemaps are slow to build and need not be fresh, so shared caches keep them for a day.
SEO_CACHE_SECONDS = 86400
SEO_CACHE_CONTROL = f"public, max-age=3600, s-maxage={SEO_CACHE_SECONDS}, stale-while-revalidate={SEO_CACHE_SECONDS}"

# The viewer route and its id parameter for each section's pages.
SECTION_ROUTES = {
    SitemapSection.CONTENT: ("get_content_front", "content_id"),
    SitemapSection.COLLECTIONS: ("get_collection_front", "collection_id"),
}


def absolute_url(request: Request, name: str, **params) -> str:
    return escape(public_url(request.url_for(name, **params)))


def xml_document(root: str, entries: list[str]) -> str:
    namespace = "http://www.sitemaps.org/schemas/sitemap/0.9"
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<{root} xmlns="{namespace}">{"".join(entries)}</{root}>'


def xml_response(document: str) -> Response:
    return Response(
        document,
        media_type="application/xml",
        headers={"Cache-Control": SEO_CACHE_CONTROL},
    )


def url_entry(location: str, updated_at: int | None = None) -> str:
    if updated_at is None:
        return f"<url><loc>{location}</loc></url>"
    date = datetime.datetime.fromtimestamp(updated_at, datetime.UTC).date()
    return f"<url><loc>{location}</loc><lastmod>{date.isoformat()}</lastmod></url>"


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots(request: Request):
    return PlainTextResponse(
        "User-agent: *\n"
        "Disallow: /render/\n"
        "Disallow: /v1/login\n"
        "Disallow: /metrics\n"
        "\n"
        f"Sitemap: {public_url(request.url_for('sitemap_index'))}\n",
        headers={"Cache-Control": SEO_CACHE_CONTROL},
    )


# The request builds the URLs but is not part of the cache key.
@cache_result(expire=SEO_CACHE_SECONDS)
async def sitemap_index_document(request: Request) -> str:
    locations = [absolute_url(request, "sitemap_pages")]
    for project in projects:
        for section in SitemapSection:
            for page in range(await sitemap_service.page_count(project, section)):
                locations.append(
                    absolute_url(
                        request,
                        "sitemap_section",
                        project=project,
                        section=section.value,
                        page=page,
                    )
                )
    return xml_document(
        "sitemapindex",
        [f"<sitemap><loc>{location}</loc></sitemap>" for location in locations],
    )


@cache_result(expire=SEO_CACHE_SECONDS)
async def sitemap_section_document(
    project: str, section: SitemapSection, page: int, request: Request
) -> str | None:
    entries = await sitemap_service.entries(project, section, page)
    if not entries:
        return None
    name, id_name = SECTION_ROUTES[section]
    return xml_document(
        "urlset",
        [
            url_entry(
                absolute_url(request, name, project=project, **{id_name: id}),
                updated_at,
            )
            for id, updated_at in entries
        ],
    )


@router.get("/sitemap.xml")
async def sitemap_index(request: Request):
    return xml_response(await sitemap_index_document(request=request))


@router.get("/sitemaps/pages.xml")
async def sitemap_pages(request: Request):
    names = ["get_index", "get_privacy", "get_tos", "get_contact", "get_credits"]
    locations = [absolute_url(request, name) for name in names]
    for project in projects:
        for name in ["get_content_library", "get_collection_library"]:
            locations.append(absolute_url(request, name, project=project))
    return xml_response(
        xml_document("urlset", [url_entry(location) for location in locations])
    )


@router.get("/sitemaps/{project}/{section}/{page:int}.xml")
async def sitemap_section(
    request: Request, project: str, section: SitemapSection, page: int
):
    if project not in projects:
        raise HTTPException(404, "Project not found")
    document = await sitemap_section_document(project, section, page, request=request)
    if document is None:
        raise HTTPException(404, "Sitemap page not found")
    return xml_response(document)
