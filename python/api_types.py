import base64
from dataclasses import dataclass
from functools import cached_property
from typing import TypeVar, List, NamedTuple

from pydantic import BaseModel


class ContentUpload(BaseModel):
    title: str
    meta: str
    data: str

    @property
    def payload(self) -> bytes:
        return base64.b64decode(self.data)


class Content(BaseModel):
    contentid: int
    userid: str
    username: str
    likes: int
    tags: List[str]
    title: str
    version: int
    meta: str
    data: str


class LiteContent(BaseModel):
    contentid: int
    userid: int
    username: str
    likes: int
    reports: int
    tags: List[str]
    title: str
    version: int


class LiteUser(BaseModel):
    userid: int
    username: str
    submission_count: int
    likes_given: int
    likes_received: int
    moderator: bool


class User(BaseModel):
    userid: int
    username: str
    likes_received: int
    likes: List[LiteContent]
    submissions: List[LiteContent]
    moderator: bool


DataType = TypeVar("DataType")


class ContentSuccess(BaseModel):
    content: Content


class ContentListSuccess(BaseModel):
    contents: List[LiteContent]
    total: int


class UserSuccess(BaseModel):
    user: User


class IsAuthResponse(BaseModel):
    authenticated: bool


class UserListSuccess(BaseModel):
    users: List[LiteUser]


class TagListSuccess(BaseModel):
    tags: List[str]


class ContentIdSuccess(BaseModel):
    contentid: int


class PlainSuccess(BaseModel):
    pass


class Error(BaseModel):
    message: str

    def to_json(self):
        return {
            "message": self.message,
        }
