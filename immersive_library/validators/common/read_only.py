from typing import Optional

from databases import Database

from immersive_library.models import ContentUpload
from immersive_library.utils import is_moderator
from immersive_library.validators.validator import Validator


class ReadOnlyValidator(Validator):
    async def pre_upload(
        self, database: Database, userid: int, content: ContentUpload
    ) -> Optional[str]:
        if is_moderator(database, userid):
            return None
        return "Project is read only"
