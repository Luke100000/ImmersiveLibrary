import base64

from fastapi import HTTPException
from pydantic import BaseModel, field_validator
from pydantic.json_schema import SkipJsonSchema


class ContentUpload(BaseModel):
    title: str
    meta: str
    data: str
    tags: list[str] | None = None

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

    def replace(self, data: bytes) -> None:
        self.data = base64.b64encode(data).decode()


class LiteUser(BaseModel):
    userid: int
    username: str
    submission_count: int
    likes_given: int
    likes_received: int
    moderator: bool


class ProjectSummary(BaseModel):
    name: str
    content_count: int


class ProjectListSuccess(BaseModel):
    projects: list[ProjectSummary]


class LiteUserSuccess(BaseModel):
    user: LiteUser


class IsAuthResponse(BaseModel):
    authenticated: bool


class TagListSuccess(BaseModel):
    tags: list[str]


class BanEntry(BaseModel):
    userid: int
    username: str


class ContentIdSuccess(BaseModel):
    contentid: int


class PlainSuccess(BaseModel):
    pass


class Error(BaseModel):
    message: str


class ContentSummary(BaseModel):
    contentid: int
    userid: int
    username: str
    likes: int
    tags: list[str]
    title: str
    version: int
    meta: str | SkipJsonSchema[None] = None
    is_liked: bool
    reports: list[str]


class Content(ContentSummary):
    meta: str
    data: str


class ContentSuccess(BaseModel):
    content: Content


class ContentListSuccess(BaseModel):
    contents: list[ContentSummary]
    has_more: bool


class UserListSuccess(BaseModel):
    users: list[LiteUser]
    has_more: bool


class TagCount(BaseModel):
    tag: str
    count: int


class TagListPage(BaseModel):
    tags: list[TagCount]
    has_more: bool
