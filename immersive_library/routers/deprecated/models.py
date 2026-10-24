from pydantic import BaseModel

from immersive_library.models import LiteContent


class User(BaseModel):
    userid: int
    username: str
    likes_received: int
    likes: list[LiteContent] | list[int]
    submissions: list[LiteContent] | list[int]
    moderator: bool


class UserSuccess(BaseModel):
    user: User
