from typing import Optional

from databases import Database

from immersive_library.models import ContentUpload


class Validator:
    async def pre_upload(
        self, database: Database, userid: int, content: ContentUpload
    ) -> Optional[str]:
        pass

    async def post_upload(self, database: Database, userid: int, contentid: int):
        pass

    async def post_report(self, database: Database, contentid: int, reason: str):
        pass
