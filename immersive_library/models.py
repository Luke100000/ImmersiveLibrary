import base64
import json
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class ContentUpload(BaseModel):
    title: str = Field(min_length=1, max_length=1024)
    meta: str = Field(max_length=262144)
    data: str = Field(max_length=2097152)
    tags: Optional[List[str]] = Field(default=None, max_length=64)

    @field_validator("meta")
    @classmethod
    def validate_meta(cls, value: str) -> str:
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("meta must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("meta must be a JSON object")
        return value

    @field_validator("data")
    @classmethod
    def validate_data(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except ValueError as exc:
            raise ValueError("data must be valid base64") from exc
        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, tags: Optional[List[str]]) -> Optional[List[str]]:
        if tags is None:
            return None
        for tag in tags:
            if not 1 <= len(tag) <= 64:
                raise ValueError("tags must contain between 1 and 64 characters")
            if "," in tag:
                raise ValueError("tags may not contain commas")
        return tags

    @property
    def payload(self) -> bytes:
        return base64.b64decode(self.data, validate=True)

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
    is_liked: Optional[bool] = None


class AuthStartRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    token_hash: Optional[str] = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    return_to: Optional[str] = Field(default=None, max_length=2048)

    @field_validator("return_to")
    @classmethod
    def validate_return_to(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not value.startswith("/") or value.startswith(("//", "/\\")):
            raise ValueError("return_to must be a local absolute path")
        return value


class AuthStartSuccess(BaseModel):
    login_url: str
    verification_code: str
    expires_in: int


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
