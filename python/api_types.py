from typing import TypeVar, List

from pydantic import BaseModel


class ContentUpload(BaseModel):
    title: str
    meta: str
    data: str


class Content(BaseModel):
    contentid: int
    username: str
    likes: int
    tags: List[str]
    title: str
    meta: str
    data: str


class User(BaseModel):
    userid: int
    username: str
    liked_received: int
    likes: List[Content]
    submissions: List[Content]
    moderator: bool


DataType = TypeVar("DataType")


class ContentSuccess(BaseModel):
    content: Content


class ContentListSuccess(BaseModel):
    contents: List[Content]


class UserSuccess(BaseModel):
    user: User


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
