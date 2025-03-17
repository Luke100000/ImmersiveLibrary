from typing import Optional

from databases import Database

from immersive_library.models import ContentUpload
from immersive_library.validators.validator import Validator


class TitleLengthValidator(Validator):
    def __init__(self, min_size: int = 1, max_size: int = 1024):
        super().__init__()

        self.min_size = min_size
        self.max_size = max_size

    async def pre_upload(
        self, database: Database, userid: int, content: ContentUpload
    ) -> Optional[str]:
        if len(content.title) < self.min_size:
            return "title too short"
        if len(content.title) > self.max_size:
            return "title too long"
