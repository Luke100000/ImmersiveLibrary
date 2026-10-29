import base64
import json
import os
from typing import Annotated

import orjson
from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query, Request
from google.auth.exceptions import GoogleAuthError, TransportError
from google.auth.transport import requests
from google.oauth2 import id_token
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, RedirectResponse, Response

from immersive_library.common import templates
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
    username: str | None = Query(None, deprecated=True, include_in_schema=False),
    token: str | None = Query(None, deprecated=True, include_in_schema=False),
) -> Response:
    return_to = None
    if state is not None:
        try:
            state_dict = orjson.loads(state)
            token = base64.b64decode(state_dict["token"], validate=True).decode("utf-8")
            username = base64.b64decode(state_dict["username"], validate=True).decode(
                "utf-8"
            )
        except (ValueError, TypeError, KeyError):
            raise HTTPException(400, "Invalid login state")

        requested_return_to = state_dict.get("return_to")
        if (
            isinstance(requested_return_to, str)
            and requested_return_to.startswith("/")
            and not requested_return_to.startswith(("//", "/\\"))
        ):
            return_to = requested_return_to

    if token is None or username is None:
        raise HTTPException(400, "Token or username missing")

    if len(token) < 16:
        raise HTTPException(400, "Token should at very least contain 16 bytes")

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
async def is_auth(
    token: str | None = None, authorization: str = Header(None)
) -> IsAuthResponse:
    user_id = await token_to_user_id(database, token, authorization)
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
            "login_uri": str(request.url_for("auth")),
            "has_cookie_consent": request.cookies.get("immersive_cookie_consent")
            == "yes",
        },
    )
