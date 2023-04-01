from enum import Enum
from typing import Any, Final, TypeVar, Generic, List

from pydantic import BaseModel, Field


class Status(Enum):
    SUCCESS = "success"
    FAIL = "fail"
    ERROR = "error"


class Content(BaseModel):
    oid: int
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


class Oid(BaseModel):
    oid: int


DataType = TypeVar("DataType")


class Success(BaseModel, Generic[DataType]):
    status: Status = Field(Status.SUCCESS, const=True)
    data: DataType


class ContentSuccess(Success):
    data: Content


class ContentListSuccess(Success):
    data: List[Content]


class UserSuccess(Success):
    data: User


class UserListSuccess(Success):
    data: List[User]


class OidSuccess(Success):
    data: Oid


class PlainSuccess(Success[None], Generic[DataType]):
    data: Final[DataType] = None

    def __init__(self, **args: Any):
        super().__init__(**args)


class Error(BaseModel):
    status: Status = Field(Status.ERROR, const=True)
    message: str

    def to_json(self):
        return {
            "status": self.status.value,
            "message": self.message,
        }


class Fail(BaseModel):
    status: Status = Status.FAIL
