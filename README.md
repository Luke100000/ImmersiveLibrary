# Immersive Library

A generic user asset library, accessible via REST API, authenticated via Google Auth.

## Features

* Read access by anyone
* Authentication via Google Sign-In
* Tags
* Likes
* Moderator status
* Banning and optionally purging users

## How to use

### Server

The server is implemented in python using FastAPI. Launch using e.g. uvicorn:

```sh
uvicorn --reload main:app
```

### Client

For most methods a user-chosen access token is required.
To acquire, call Google Sign-In and forward the response to

```
/v1/auth
```

The state var needs to be a json object with the following keys:
* `username` A username as shown to other users
* `token` A freely chosen token to authenticate with, sha256 hashed. Use the original token as Bearer token for all other requests.

## API

Access the documentation in your browser at `/redoc` or `/docs`.