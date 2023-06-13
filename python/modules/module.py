from sqlite3 import Connection

from api_types import ContentUpload


class Module:
    def __init__(self, con: Connection) -> None:
        super().__init__()

        self.con = con

    def pre_upload(self, content: ContentUpload) -> str:
        pass

    def post_upload(self, contentid: int):
        pass
