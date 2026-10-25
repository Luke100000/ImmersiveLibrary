# Immersive Library

A generic user asset library, accessible via REST API, authenticated via Google Auth.

## Features

* Public read, authenticated write
* Authentication via Google Sign-In
* Tags, Likes, Reports
* Personal collections with optional public sharing
* Moderation tools

## Server

The server is implemented in python using FastAPI.

```sh
python -m immersive_library.database.prepare
uvicorn --reload immersive_library.main:app
```

```sh
docker compose up
```

Existing databases are migrated during setup. Back up the database before updating.

## Client

For some endpoints a user-chosen access token is required.

Call `/v1/login` to let the server handle the Google Sign-In.

The state var needs to be a JSON object with the following keys:

* `username` A username as shown to other users, base64 encoded.
* `token` A freely chosen token to authenticate with, sha256 hashed, base64 encoded.
    * Use the original token as a Bearer token for all other requests.
    * There can only be 10 logins, after which the oldest token gets pruned.

## API

Access the documentation in your browser at `/redoc` or `/docs`.

### Content

A piece of content consists of:

* `content_id` A unique identifier
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

### Collections

Named, user-owned collections of content within a project.
Collections are private by default; owners can make them public.
Deleting a collection leaves its content in the library.

### Reports

Reports are used to flag content for moderation, with a custom reason enum.
`DEFAULT` is used for user-based heuristic moderation.
Additional reports can be handled in the project validators.

### Projects

Projects define a collection of content and can have several validators to reject, or post-process content.
The `default` fallback can allow user-chosen projects.
See `main.py` for examples.
