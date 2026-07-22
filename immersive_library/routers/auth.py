import base64
import os
import secrets
import time
from typing import Annotated, Optional
from urllib.parse import urlparse

import orjson
from fastapi import APIRouter, Cookie, Form, Header, HTTPException, Request
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests
from google.oauth2 import id_token
from starlette.responses import HTMLResponse, RedirectResponse, Response

from immersive_library.common import database, templates
from immersive_library.models import AuthStartRequest, AuthStartSuccess, IsAuthResponse
from immersive_library.utils import (
    SESSION_COOKIE,
    enforce_rate_limit,
    login_user,
    revoke_token,
    sha256,
    token_to_userid,
)

router = APIRouter(tags=["Auth"])

AUTH_REQUEST_TTL_SECONDS = int(os.getenv("AUTH_REQUEST_TTL_SECONDS", "600"))
AUTH_REQUEST_COOKIE = "immersive_auth_request"
AUTH_BROWSER_COOKIE = "immersive_auth_browser"
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _secure_cookies(request: Request) -> bool:
    setting = os.getenv("COOKIE_SECURE", "auto").lower()
    if setting in {"1", "true", "yes"}:
        return True
    if setting in {"0", "false", "no"}:
        return False
    public_base_url = os.getenv("PUBLIC_BASE_URL", "")
    return urlparse(public_base_url).scheme == "https" or request.url.scheme == "https"


def _verification_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return raw[:4] + "-" + raw[4:]


async def _create_auth_request(
    token_hash: Optional[str], username: str, return_to: Optional[str]
) -> tuple[str, str]:
    now = int(time.time())
    await database.execute(
        "DELETE FROM auth_requests WHERE expires_at <= :now", {"now": now}
    )

    request_id = secrets.token_urlsafe(32)
    verification_code = _verification_code()
    await database.execute(
        """
        INSERT INTO auth_requests
            (request_id, token_hash, username, return_to, verification_code, browser_nonce_hash, expires_at)
        VALUES
            (:request_id, :token_hash, :username, :return_to, :verification_code, NULL, :expires_at)
        """,
        {
            "request_id": request_id,
            "token_hash": token_hash,
            "username": username,
            "return_to": return_to,
            "verification_code": verification_code,
            "expires_at": now + AUTH_REQUEST_TTL_SECONDS,
        },
    )
    return request_id, verification_code


def _state_payload(request_id: str, browser_nonce: str) -> dict[str, str]:
    return {"request_id": request_id, "browser_nonce": browser_nonce}


def _decode_state(state: str) -> tuple[str, str]:
    try:
        payload = orjson.loads(state)
        return str(payload["request_id"]), str(payload["browser_nonce"])
    except Exception as exc:
        raise HTTPException(400, "Invalid authentication state") from exc


def _decode_legacy_state(state: str) -> tuple[str, str]:
    try:
        # MCA 1.20.1/1.21.1 append standard Base64 directly to the query string.
        # Some URL decoders translate '+' into spaces, so normalize it back first.
        payload = orjson.loads(base64.b64decode(state.replace(" ", "+")))
        token_hash = base64.b64decode(payload["token"]).decode("utf-8").lower()
        username = base64.b64decode(payload["username"]).decode("utf-8")
    except Exception as exc:
        raise HTTPException(400, "Invalid legacy authentication state") from exc

    if len(token_hash) != 64 or any(c not in "0123456789abcdef" for c in token_hash):
        raise HTTPException(400, "Invalid legacy token hash")
    if not username:
        raise HTTPException(400, "Username missing")

    return token_hash, username


async def _pending_request(request_id: str):
    pending = await database.fetch_one(
        "SELECT * FROM auth_requests WHERE request_id=:request_id",
        {"request_id": request_id},
    )
    if pending is None or pending["expires_at"] <= int(time.time()):
        await database.execute(
            "DELETE FROM auth_requests WHERE request_id=:request_id",
            {"request_id": request_id},
        )
        raise HTTPException(400, "Authentication request expired")
    return pending


async def _claim_pending_request_by_code(
    code: str, browser_cookie: Optional[str] = None
):
    normalized = code.strip().upper()
    now = int(time.time())
    matches = await database.fetch_all(
        """
        SELECT request_id
        FROM auth_requests
        WHERE verification_code=:code AND expires_at > :now
        LIMIT 2
        """,
        {"code": normalized, "now": now},
    )
    if len(matches) != 1:
        raise HTTPException(400, "Invalid or expired verification code")

    pending = await _pending_request(matches[0]["request_id"])
    if pending["browser_nonce_hash"] is not None:
        if browser_cookie is not None and secrets.compare_digest(
            pending["browser_nonce_hash"], sha256(browser_cookie)
        ):
            return pending, browser_cookie
        raise HTTPException(400, "Verification code has already been used")

    browser_nonce = secrets.token_urlsafe(32)
    pending = await database.fetch_one(
        """
        UPDATE auth_requests
        SET browser_nonce_hash=:nonce
        WHERE request_id=:request_id
          AND browser_nonce_hash IS NULL
          AND expires_at > :now
        RETURNING *
        """,
        {
            "nonce": sha256(browser_nonce),
            "request_id": matches[0]["request_id"],
            "now": now,
        },
    )
    if pending is None:
        raise HTTPException(400, "Verification code has already been used")
    return pending, browser_nonce


async def _render_google_login(
    request: Request,
    pending,
    browser_nonce: Optional[str] = None,
    show_verification_code: bool = True,
) -> Response:
    if not os.getenv("PUBLIC_BASE_URL"):
        raise HTTPException(503, "PUBLIC_BASE_URL is not configured")
    if not os.getenv("CLIENT_ID"):
        raise HTTPException(503, "Google OAuth CLIENT_ID is not configured")
    if pending["browser_nonce_hash"] is None:
        browser_nonce = secrets.token_urlsafe(32)
        await database.execute(
            "UPDATE auth_requests SET browser_nonce_hash=:nonce WHERE request_id=:request_id",
            {"nonce": sha256(browser_nonce), "request_id": pending["request_id"]},
        )
    elif browser_nonce is None or not secrets.compare_digest(
        pending["browser_nonce_hash"], sha256(browser_nonce)
    ):
        raise HTTPException(401, "Authentication browser does not match")

    response = templates.TemplateResponse(
        "login.jinja",
        {
            "request": request,
            "state": _state_payload(pending["request_id"], browser_nonce),
            "client_id": os.getenv("CLIENT_ID"),
            "login_uri": os.getenv("PUBLIC_BASE_URL", "").rstrip("/") + "/v2/auth/complete",
            "verification_code": (
                pending["verification_code"]
                if show_verification_code and pending["token_hash"] is not None
                else None
            ),
            "has_cookie_consent": request.cookies.get("immersive_cookie_consent") == "yes",
        },
    )
    secure_cookies = _secure_cookies(request)
    response.set_cookie(
        AUTH_BROWSER_COOKIE,
        browser_nonce,
        max_age=AUTH_REQUEST_TTL_SECONDS,
        httponly=True,
        secure=secure_cookies,
        samesite="none" if secure_cookies else "lax",
        path="/",
    )
    return response


@router.post("/v2/auth/start", response_model=AuthStartSuccess)
async def start_auth(
    request: Request, response: Response, auth_request: AuthStartRequest
) -> AuthStartSuccess:
    await enforce_rate_limit(request, "auth-start", 20, 600)
    token_hash = auth_request.token_hash.lower() if auth_request.token_hash else None
    request_id, code = await _create_auth_request(
        token_hash, auth_request.username, auth_request.return_to
    )

    # Browser-originated requests have no client token hash. This HttpOnly cookie
    # lets the same browser continue without manually entering the device code.
    if token_hash is None:
        response.set_cookie(
            AUTH_REQUEST_COOKIE,
            request_id,
            max_age=AUTH_REQUEST_TTL_SECONDS,
            httponly=True,
            secure=_secure_cookies(request),
            samesite="lax",
            path="/",
        )

    return AuthStartSuccess(
        login_url=(
            "/v2/login"
            if token_hash is None
            else f"/v2/login?code={code}"
        ),
        verification_code=code,
        expires_in=AUTH_REQUEST_TTL_SECONDS,
    )


@router.get("/v2/login", response_class=HTMLResponse)
async def get_login_v2(
    request: Request,
    code: Optional[str] = None,
    auth_request_cookie: Optional[str] = Cookie(None, alias=AUTH_REQUEST_COOKIE),
    browser_cookie: Optional[str] = Cookie(None, alias=AUTH_BROWSER_COOKIE),
) -> Response:
    if code is not None:
        await enforce_rate_limit(request, "auth-code", 30, 600)
        pending, browser_nonce = await _claim_pending_request_by_code(code, browser_cookie)
        response = RedirectResponse("/v2/login", status_code=303)
        secure_cookies = _secure_cookies(request)
        response.set_cookie(
            AUTH_REQUEST_COOKIE,
            pending["request_id"],
            max_age=AUTH_REQUEST_TTL_SECONDS,
            httponly=True,
            secure=secure_cookies,
            samesite="lax",
            path="/",
        )
        response.set_cookie(
            AUTH_BROWSER_COOKIE,
            browser_nonce,
            max_age=AUTH_REQUEST_TTL_SECONDS,
            httponly=True,
            secure=secure_cookies,
            samesite="none" if secure_cookies else "lax",
            path="/",
        )
        return response

    if auth_request_cookie is None:
        raise HTTPException(400, "No pending authentication request")

    pending = await _pending_request(auth_request_cookie)
    if pending["browser_nonce_hash"] is not None:
        if browser_cookie is None or not secrets.compare_digest(
            pending["browser_nonce_hash"], sha256(browser_cookie)
        ):
            raise HTTPException(401, "Authentication browser does not match")
    return await _render_google_login(request, pending, browser_cookie)


@router.post("/v2/auth/complete", name="complete_auth_v2")
async def complete_auth_v2(
    request: Request,
    credential: Annotated[str, Form()],
    state: Annotated[str, Form()],
    browser_cookie: Optional[str] = Cookie(None, alias=AUTH_BROWSER_COOKIE),
) -> Response:
    await enforce_rate_limit(request, "auth-complete", 30, 600)
    request_id, browser_nonce = _decode_state(state)
    pending = await _pending_request(request_id)
    if not secrets.compare_digest(
        pending["browser_nonce_hash"] or "", sha256(browser_nonce)
    ):
        raise HTTPException(401, "Authentication state does not match")
    secure_cookies = _secure_cookies(request)
    if secure_cookies and not secrets.compare_digest(
        browser_cookie or "", browser_nonce
    ):
        raise HTTPException(401, "Authentication browser does not match")

    client_id = os.getenv("CLIENT_ID")
    if not client_id:
        raise HTTPException(503, "Google OAuth CLIENT_ID is not configured")

    try:
        info = id_token.verify_oauth2_token(credential, requests.Request(), client_id)
    except (ValueError, google_auth_exceptions.GoogleAuthError) as exc:
        raise HTTPException(401, "Validation failed") from exc

    consumed = await database.fetch_one(
        "DELETE FROM auth_requests WHERE request_id=:request_id AND expires_at > :now RETURNING request_id",
        {"request_id": request_id, "now": int(time.time())},
    )
    if consumed is None:
        raise HTTPException(400, "Authentication request already used or expired")

    raw_session_token = None
    token_hash = pending["token_hash"]
    if token_hash is None:
        raw_session_token = secrets.token_urlsafe(48)
        token_hash = sha256(raw_session_token)

    await login_user(database, info["sub"], pending["username"], token_hash)

    if pending["return_to"] is not None:
        response = RedirectResponse(pending["return_to"], status_code=303)
    else:
        response = templates.TemplateResponse("success.jinja", {"request": request})

    if raw_session_token is not None:
        response.set_cookie(
            SESSION_COOKIE,
            raw_session_token,
            max_age=int(os.getenv("AUTH_TOKEN_TTL_SECONDS", str(30 * 24 * 60 * 60))),
            httponly=True,
            secure=secure_cookies,
            samesite="lax",
            path="/",
        )
    response.delete_cookie(AUTH_REQUEST_COOKIE, path="/")
    response.delete_cookie(AUTH_BROWSER_COOKIE, path="/")
    return response


@router.get("/v1/auth", summary="Check if user is authenticated")
async def is_auth(
    authorization: Optional[str] = Header(None),
    session_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE),
) -> IsAuthResponse:
    userid = await token_to_userid(database, authorization, session_token)
    return IsAuthResponse(authenticated=userid is not None)


@router.delete("/v2/auth/token")
async def logout(
    response: Response,
    authorization: Optional[str] = Header(None),
    session_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE),
) -> dict:
    await revoke_token(database, authorization, session_token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {}


# TODO: Remove when MCA 1.20.1 and 1.21.1 legacy login support is dropped.
@router.get(
    "/v1/login",
    response_class=HTMLResponse,
    deprecated=True,
    summary="Login (legacy compatibility)",
)
async def get_login_v1(request: Request, state: str) -> Response:
    """Bridge older MCA clients onto the hardened v2 completion flow."""
    await enforce_rate_limit(request, "auth-legacy-login", 20, 600)
    token_hash, username = _decode_legacy_state(state)

    request_id, _ = await _create_auth_request(token_hash, username, None)
    pending = await _pending_request(request_id)
    return await _render_google_login(
        request, pending, show_verification_code=False
    )
