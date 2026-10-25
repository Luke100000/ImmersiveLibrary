from databases import Database

from immersive_library.models import ContentUpload
from immersive_library.utils import is_moderator
from immersive_library.validators.validator import Validator


class ReadOnlyValidator(Validator):
    async def pre_upload(
        self, database: Database, user_id: int, content: ContentUpload
    ) -> str | None:
        if await is_moderator(database, user_id):
            return None
        return "Project is read only"
