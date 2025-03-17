import base64
import json
import os
from typing import Annotated, Optional

import orjson
from fastapi import APIRouter
from fastapi import Form, Request, HTTPException, Header
from google.auth.transport import requests
from google.oauth2 import id_token
from starlette.responses import HTMLResponse

from immersive_library.common import database, templates
from immersive_library.models import (
    IsAuthResponse,
    Error,
)
from immersive_library.utils import (
    login_user,
    token_to_userid,
)

router = APIRouter(tags=["Auth"])


@router.post(
    "/v1/auth",
    responses={401: {"model": Error}, 400: {"model": Error}},
    summary="Authenticate user",
)
async def auth(
    request: Request,
    credential: Annotated[str, Form()],
    state: Annotated[Optional[str], Form()] = None,
    username: Optional[str] = None,
    token: Optional[str] = None,
) -> HTMLResponse:
    if state is not None:
        state_dict = orjson.loads(state)
        token = base64.b64decode(state_dict.get("token")).decode("utf-8")
        username = base64.b64decode(state_dict.get("username")).decode("utf-8")

    if token is None or username is None:
        raise HTTPException(400, "Token or username missing")

    if len(token) < 16:
        raise HTTPException(400, "Token should at very least contain 16 bytes")

    try:
        info = id_token.verify_oauth2_token(
            credential, requests.Request(), os.getenv("CLIENT_ID")
        )

        userid = info["sub"]

        # Update session for user
        await login_user(database, userid, username, token)

        return templates.TemplateResponse("success.jinja", {"request": request})
    except ValueError:
        raise HTTPException(401, "Validation failed")


@router.get(
    "/v1/auth",
    summary="Check if user is authenticated",
)
async def is_auth(
    token: Optional[str] = None, authorization: str = Header(None)
) -> IsAuthResponse:
    executor_userid = await token_to_userid(database, token, authorization)
    return IsAuthResponse(authenticated=executor_userid is not None)


@router.get(
    "/v1/login",
    summary="Login",
)
async def get_login(request: Request, state: str) -> HTMLResponse:
    return templates.TemplateResponse(
        "login.jinja",
        {"request": request, "state": json.loads(base64.b64decode(state))},
    )
