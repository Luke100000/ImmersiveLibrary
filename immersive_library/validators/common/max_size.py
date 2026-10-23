from typing import Optional

from databases import Database

from immersive_library.models import ContentUpload
from immersive_library.validators.validator import Validator


class MaxSizeValidator(Validator):
    def __init__(self, max_size: int):
        """
        :param max_size: The maximum size for the data field in bytes.
        """
        super().__init__()

        self.max_size = max_size

    async def pre_upload(
        self, database: Database, userid: int, content: ContentUpload
    ) -> Optional[str]:
        if len(content.payload) > self.max_size:
            return "data too large"
        return None
