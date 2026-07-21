# Immersive Library

A generic user asset library, accessible via REST API, authenticated via Google Auth.

## Features

* Public read, authenticated write
* Authentication via Google Sign-In
* Tags, Likes, Reports
* Moderation tools

## Server

The server is implemented in python using FastAPI.

```sh
uvicorn --reload main:app
```

```sh
docker compose up
```

## Client

Authentication starts with `POST /v2/auth/start`.

* Browser clients omit `token_hash`. The server creates an HttpOnly session cookie after Google Sign-In.
* Native clients generate a private access token, send only its SHA-256 hash as `token_hash`, and show the returned verification code to the user. The login page requires that code before Google Sign-In can bind the token to the account.
* Native clients use the original private token in the `Authorization: Bearer <token>` header.
* `DELETE /v2/auth/token` revokes the current browser session or bearer token.
* New access tokens expire. The default lifetime is 30 days and can be configured with `AUTH_TOKEN_TTL_SECONDS`.
* Tokens created before this migration receive a 90-day grace period by default; configure it with `LEGACY_TOKEN_GRACE_SECONDS`.

`/v2/content/{project}` remains the legacy paginated response and omits `is_liked`. Updated clients use `/v3/content/{project}`, which includes requester-specific `is_liked`.

Security-related environment variables include `AUTH_TOKEN_TTL_SECONDS`, `LEGACY_TOKEN_GRACE_SECONDS`, `AUTH_REQUEST_TTL_SECONDS`, `MAX_REQUEST_BYTES`, `RENDER_BASE_URL`, `RENDER_CONCURRENCY_LIMIT`, `COOKIE_SECURE`, and `PUBLIC_BASE_URL`.

## API

Access the documentation in your browser at `/redoc` or `/docs`.

### Content

A piece of content consists of:

* `contentid` A unique identifier
* `title` A short title
* `meta` An unstructured metadata dictionary, JSON compliant
* `data` Arbitrary (binary) data, base64 encoded during transfer
* `version` An incrementing version number when the content has been changed

Content should be locally cached by the client and only updated when the version number changes.

### Tags

Tags are used for filtering or marking content, either set by the user or as part of project validation.

### Likes

Simple like/favorite system, one like per user per content.
Likes are considered public information.

### Reports

Reports are used to flag content for moderation, with a custom reason enum.
`DEFAULT` is used for user-based heuristic moderation.
Additional reports can be handled in the project validators.

### Projects

Projects define a collection of content and can have several validators to reject, or post-process content.
The `default` fallback can allow user-chosen projects.
See `main.py` for examples.