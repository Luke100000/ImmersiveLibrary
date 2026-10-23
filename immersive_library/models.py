import base64
from typing import Any, Dict, List, Optional, Union

from fastapi import HTTPException
from pydantic import BaseModel, field_validator


class ContentUpload(BaseModel):
    title: str
    meta: str
    data: str
    tags: Optional[List[str]] = None

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, tags: list[str] | None) -> list[str] | None:
        try:
            for tag in tags or []:
                tag.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise HTTPException(400, "Tags contain invalid Unicode") from exc

        return tags

    @property
    def payload(self) -> bytes:
        try:
            return base64.b64decode(self.data, validate=True)
        except ValueError as exc:
            raise HTTPException(400, "Invalid Base64 data") from exc

    def replace(self, data: bytes):
        self.data = base64.b64encode(data).decode()


class Content(BaseModel):
    contentid: int
    userid: int
    username: str
    likes: int
    tags: List[str]
    title: str
    version: int
    meta: Union[str, Dict[str, Any]]
    data: str


class LiteContent(BaseModel):
    contentid: int
    userid: int
    username: str
    likes: int
    tags: List[str]
    title: str
    version: int
    meta: Optional[Union[str, Dict[str, Any]]] = None


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
    likes: Union[List[LiteContent], List[int]]
    submissions: Union[List[LiteContent], List[int]]
    moderator: bool


class ProjectSummary(BaseModel):
    name: str
    content_count: int


class ProjectListSuccess(BaseModel):
    projects: List[ProjectSummary]


class ContentSuccess(BaseModel):
    content: Content


class ContentListSuccess(BaseModel):
    contents: List[LiteContent]


class UserSuccess(BaseModel):
    user: User


class LiteUserSuccess(BaseModel):
    user: LiteUser


class IsAuthResponse(BaseModel):
    authenticated: bool


class UserListSuccess(BaseModel):
    users: List[LiteUser]


class TagListSuccess(BaseModel):
    tags: List[str]


class TagDictSuccess(BaseModel):
    tags: Dict[str, int]


class ContentIdSuccess(BaseModel):
    contentid: int


class BanEntry(BaseModel):
    userid: int
    username: str


class PlainSuccess(BaseModel):
    pass


class Error(BaseModel):
    message: str
