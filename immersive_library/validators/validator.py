from databases import Database

from immersive_library.models import ContentUpload


class Validator:
    async def pre_upload(
        self, database: Database, user_id: int, content: ContentUpload
    ) -> str | None:
        return None

    async def post_upload(
        self, database: Database, user_id: int, content_id: int
    ) -> str | None:
        return None

    async def pre_report(
        self, database: Database, user_id: int, content_id: int, reason: str
    ) -> str | None:
        return None

    async def post_report(
        self, database: Database, user_id: int, content_id: int, reason: str
    ) -> str | None:
        return None
