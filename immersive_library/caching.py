from collections.abc import Callable

from starlette.requests import Request
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

PRIVATE_CACHE_CONTROL = "private, no-store"
STATIC_CACHE_CONTROL = "public, max-age=3600, s-maxage=14400, must-revalidate"


def public_cache(*, when: Callable[[Request], bool] | None = None):
    """Allow shared caching, using the endpoint's existing cache lifetime."""

    def annotate(endpoint):
        endpoint.public_cache = when or (lambda request: True)
        return endpoint

    return annotate


class CachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = STATIC_CACHE_CONTROL
        return response


def apply_cache_policy(request: Request, response: Response) -> None:
    policy = getattr(request.scope.get("endpoint"), "public_cache", None)
    cache_control = response.headers.get("Cache-Control", "")
    response.headers.add_vary_header("Authorization")

    if (
        request.method not in {"GET", "HEAD"}
        or response.status_code not in {200, 304}
        or "authorization" in request.headers
        or "token" in request.query_params
        or "Set-Cookie" in response.headers
        or any(
            directive.strip().lower() == "no-store"
            for directive in request.headers.get("Cache-Control", "").split(",")
        )
        or (policy is not None and not policy(request))
    ):
        response.headers["Cache-Control"] = PRIVATE_CACHE_CONTROL
        return

    # fastapi-cache supplies the remaining lifetime on cache hits.
    if policy is not None and cache_control.startswith("max-age="):
        response.headers["Cache-Control"] = f"public, {cache_control}, must-revalidate"
    elif not cache_control.startswith("public,"):
        response.headers["Cache-Control"] = PRIVATE_CACHE_CONTROL
