from typing import Any, Final, TypeVar, Generic, List

from pydantic import BaseModel, Field


class Content(BaseModel):
    itemid: int
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


class ItemIdResponse(BaseModel):
    itemid: int


DataType = TypeVar("DataType")


class Success(BaseModel, Generic[DataType]):
    status: str = Field("success", const=True)
    data: DataType


class ContentSuccess(Success):
    data: Content


class ContentListSuccess(Success):
    data: List[Content]


class UserSuccess(Success):
    data: User


class UserListSuccess(Success):
    data: List[User]


class TagListSuccess(Success):
    data: List[str]


class ItemIdSuccess(Success):
    data: ItemIdResponse


class PlainSuccess(Success[None], Generic[DataType]):
    data: Final[DataType] = None

    def __init__(self, **args: Any):
        super().__init__(**args)


class Error(BaseModel):
    status: str = Field("error", const=True)
    message: str

    def to_json(self):
        return {
            "status": self.status,
            "message": self.message,
        }


class Fail(BaseModel):
    status: str = Field("fail", const=True)
