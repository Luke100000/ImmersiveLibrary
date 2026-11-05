import base64
import json
import os
import re
from typing import Annotated

import orjson
from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from google.auth.exceptions import GoogleAuthError, TransportError
from google.auth.transport import requests
from google.oauth2 import id_token
from starlette.concurrency import run_in_threadpool
from starlette.responses import (
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)

from immersive_library.common import public_url, templates
from immersive_library.database import database
from immersive_library.models import (
    Error,
    IsAuthResponse,
)
from immersive_library.ratelimit import AUTH
from immersive_library.utils import (
    login_user,
    token_to_user_id,
)

router = APIRouter(tags=["Auth"])

MAX_USERNAME_LENGTH = 32


@router.post(
    "/v1/auth",
    responses={401: {"model": Error}, 400: {"model": Error}},
    summary="Authenticate user",
    dependencies=[Depends(AUTH)],
)
async def auth(
    request: Request,
    credential: Annotated[str, Form()],
    state: Annotated[str | None, Form()] = None,
) -> Response:
    # Outdated clients log in with query parameters instead of a login state.
    if state is None:
        return PlainTextResponse(
            "This version can no longer sign in to Immersive Library. "
            "Update to the latest version to sign in. "
            "You can still browse the library without an account.",
            status_code=400,
        )

    try:
        state_dict = orjson.loads(state)
        token = base64.b64decode(state_dict["token"], validate=True).decode("utf-8")
        username = base64.b64decode(state_dict["username"], validate=True).decode(
            "utf-8"
        )
    except (ValueError, TypeError, KeyError):
        raise HTTPException(400, "Invalid login state")

    return_to = None
    requested_return_to = state_dict.get("return_to")
    if (
        isinstance(requested_return_to, str)
        and requested_return_to.startswith("/")
        and not requested_return_to.startswith(("//", "/\\"))
    ):
        return_to = requested_return_to

    username = username.strip()[:MAX_USERNAME_LENGTH]
    if not username:
        raise HTTPException(400, "Username missing")

    # Clients send the SHA-256 hex digest of their token, never the token itself.
    if not re.fullmatch(r"[0-9a-f]{64}", token):
        raise HTTPException(400, "Token must be a SHA-256 hex digest")

    try:
        info = await run_in_threadpool(
            id_token.verify_oauth2_token,
            credential,
            requests.Request(),
            os.getenv("CLIENT_ID", ""),
        )

        user_id = info["sub"]

        # Update session for user
        await login_user(database, user_id, username, token)

        if return_to is not None:
            return RedirectResponse(return_to, status_code=303)

        return templates.TemplateResponse(request, "success.jinja")
    except TransportError:
        raise HTTPException(503, "Authentication service unavailable")
    except (ValueError, GoogleAuthError):
        raise HTTPException(401, "Validation failed")


@router.get("/v1/auth", summary="Check if user is authenticated")
async def is_auth(authorization: str = Header(None)) -> IsAuthResponse:
    user_id = await token_to_user_id(database, authorization)
    return IsAuthResponse(authenticated=user_id is not None)


@router.get("/v1/login", summary="Login")
async def get_login(request: Request, state: str) -> HTMLResponse:
    try:
        state_dict = json.loads(base64.b64decode(state, validate=True))
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid login state")

    if not isinstance(state_dict, dict):
        raise HTTPException(400, "Invalid login state")

    return templates.TemplateResponse(
        request,
        "login.jinja",
        {
            "state": state_dict,
            "client_id": os.getenv("CLIENT_ID"),
            "login_uri": public_url(request.url_for("auth")),
            "has_cookie_consent": request.cookies.get("immersive_cookie_consent")
            == "yes",
        },
    )
