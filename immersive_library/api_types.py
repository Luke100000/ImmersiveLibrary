import base64
from typing import List, Dict, Union, Any, Optional

from pydantic import BaseModel


class ContentUpload(BaseModel):
    title: str
    meta: str
    data: str

    @property
    def payload(self) -> bytes:
        return base64.b64decode(self.data)

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
    meta: Optional[Union[str, Dict[str, Any]]]


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
