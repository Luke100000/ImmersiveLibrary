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
cd python
uvicorn --reload main:app
```

### Client

For most methods a user-chosen access token is required. To acquire, call Google Sign-In and forward the response to

```
/v1/auth?token=YOUR_TOKEN
```

A Java example is included in the repo. The token should be securely random and sufficient in size.

## API

Access the documentation in your browser at `/redoc` or `/docs`.