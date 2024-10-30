from typing import Optional

from databases import Database

from api_types import ContentUpload


class Module:
    def __init__(self, database: Database) -> None:
        super().__init__()

        self.database = database

    async def pre_upload(self, content: ContentUpload) -> Optional[str]:
        pass

    async def post_upload(self, contentid: int):
        pass

    async def post_report(self, contentid: int, reason: str):
        pass
