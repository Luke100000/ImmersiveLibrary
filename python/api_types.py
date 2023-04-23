from typing import TypeVar, List

from pydantic import BaseModel


class ContentUpload(BaseModel):
    title: str
    meta: str
    data: str


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
    tags: List[str]
    title: str
    version: int


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


class UserSuccess(BaseModel):
    user: User


class IsAuthResponse(BaseModel):
    authenticated: bool


class UserListSuccess(BaseModel):
    users: List[User]


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
