from typing import Any

from pydantic import BaseModel

from immersive_library.models import LiteUser


class Content(BaseModel):
    contentid: int
    userid: int
    username: str
    likes: int
    tags: list[str]
    title: str
    version: int
    meta: str | dict[str, Any]
    data: str


class LiteContent(BaseModel):
    contentid: int
    userid: int
    username: str
    likes: int
    tags: list[str]
    title: str
    version: int
    meta: str | dict[str, Any] | None = None


class ContentSuccess(BaseModel):
    content: Content


class ContentListSuccess(BaseModel):
    contents: list[LiteContent]


class UserListSuccess(BaseModel):
    users: list[LiteUser]


class TagDictSuccess(BaseModel):
    tags: dict[str, int]


class User(BaseModel):
    userid: int
    username: str
    likes_received: int
    likes: list[LiteContent] | list[int]
    submissions: list[LiteContent] | list[int]
    moderator: bool


class UserSuccess(BaseModel):
    user: User
