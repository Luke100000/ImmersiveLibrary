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
    title: str
    meta: str
    data: str


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
