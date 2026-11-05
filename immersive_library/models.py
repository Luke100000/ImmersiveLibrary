import base64
from typing import Annotated

from fastapi import HTTPException
from pydantic import BaseModel, StringConstraints, field_validator
from pydantic.json_schema import SkipJsonSchema

MAX_META_LENGTH = 16384
MAX_TAGS = 200
MAX_TAG_LENGTH = 100


def validate_tag(tag: str) -> None:
    if len(tag) > MAX_TAG_LENGTH:
        raise HTTPException(400, "Tag too long")
    try:
        tag.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise HTTPException(400, "Tags contain invalid Unicode") from exc


class ContentUpload(BaseModel):
    title: str
    meta: str
    data: str
    tags: list[str] | None = None

    @field_validator("meta")
    @classmethod
    def validate_meta(cls, meta: str) -> str:
        if len(meta) > MAX_META_LENGTH:
            raise HTTPException(400, "Meta too long")
        return meta

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, tags: list[str] | None) -> list[str] | None:
        if tags is not None and len(tags) > MAX_TAGS:
            raise HTTPException(400, "Too many tags")
        for tag in tags or []:
            validate_tag(tag)
        return tags

    @property
    def payload(self) -> bytes:
        try:
            return base64.b64decode(self.data, validate=True)
        except ValueError as exc:
            raise HTTPException(400, "Invalid Base64 data") from exc

    def replace(self, data: bytes) -> None:
        self.data = base64.b64encode(data).decode()


class User(BaseModel):
    user_id: int
    username: str
    submission_count: int
    likes_given: int
    likes_received: int
    recent_likes_received: int
    average_report_score: float
    moderator: bool
    banned: bool
    created_at: int
    preview_ids: list[int] | SkipJsonSchema[None] = None


class ProjectSummary(BaseModel):
    name: str
    content_count: int


class ProjectListSuccess(BaseModel):
    projects: list[ProjectSummary]


class UserSuccess(BaseModel):
    user: User


class IsAuthResponse(BaseModel):
    authenticated: bool


class TagListSuccess(BaseModel):
    tags: list[str]


class PlainSuccess(BaseModel):
    pass


class Error(BaseModel):
    message: str


class ContentSummary(BaseModel):
    content_id: int
    user_id: int
    username: str
    likes: int
    tags: list[str]
    title: str
    version: int
    created_at: int
    updated_at: int
    meta: str | SkipJsonSchema[None] = None
    data: str | SkipJsonSchema[None] = None
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
    users: list[User]
    has_more: bool


class TagCount(BaseModel):
    tag: str
    count: int


class TagListPage(BaseModel):
    tags: list[TagCount]
    has_more: bool


CollectionTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
CollectionDescription = Annotated[str, StringConstraints(max_length=2000)]


class CollectionCreate(BaseModel):
    title: CollectionTitle
    description: CollectionDescription = ""
    is_public: bool = False


class CollectionUpdate(BaseModel):
    title: CollectionTitle | SkipJsonSchema[None] = None
    description: CollectionDescription | SkipJsonSchema[None] = None
    is_public: bool | SkipJsonSchema[None] = None

    @field_validator("title", "description", "is_public")
    @classmethod
    def reject_null(cls, value: str | bool | None) -> str | bool:
        if value is None:
            raise ValueError("Collection fields cannot be null")
        return value


class Collection(BaseModel):
    collection_id: int
    user_id: int
    username: str
    project: str
    title: str
    description: str
    is_public: bool
    created_at: int
    updated_at: int
    content_count: int
    is_owner: bool
    contains_content: bool | SkipJsonSchema[None] = None
    # The assets added last, in lists only.
    preview_ids: list[int] | SkipJsonSchema[None] = None


class CollectionSuccess(BaseModel):
    collection: Collection


class CollectionListSuccess(BaseModel):
    collections: list[Collection]
    has_more: bool
