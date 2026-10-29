from typing import Any

from pydantic import BaseModel


class LegacyContentIdSuccess(BaseModel):
    contentid: int


class LegacyBanEntry(BaseModel):
    userid: int
    username: str


class LegacyLiteUser(BaseModel):
    userid: int
    username: str
    submission_count: int
    likes_given: int
    likes_received: int
    moderator: bool


class LegacyLiteUserSuccess(BaseModel):
    user: LegacyLiteUser


class LegacyContent(BaseModel):
    contentid: int
    userid: int
    username: str
    likes: int
    tags: list[str]
    title: str
    version: int
    meta: str | dict[str, Any]
    data: str


class LegacyLiteContent(BaseModel):
    contentid: int
    userid: int
    username: str
    likes: int
    tags: list[str]
    title: str
    version: int
    meta: str | dict[str, Any] | None = None


class LegacyContentSuccess(BaseModel):
    content: LegacyContent


class LegacyContentListSuccess(BaseModel):
    contents: list[LegacyLiteContent]


class LegacyUserListSuccess(BaseModel):
    users: list[LegacyLiteUser]


class LegacyTagDictSuccess(BaseModel):
    tags: dict[str, int]


class LegacyUser(BaseModel):
    userid: int
    username: str
    likes_received: int
    likes: list[LegacyLiteContent] | list[int]
    submissions: list[LegacyLiteContent] | list[int]
    moderator: bool


class LegacyUserSuccess(BaseModel):
    user: LegacyUser
