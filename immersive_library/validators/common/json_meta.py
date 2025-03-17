from typing import Optional

from databases import Database
from pydantic import ValidationError, BaseModel

from immersive_library.models import ContentUpload
from immersive_library.validators.validator import Validator


class JsonMetaValidator(Validator):
    def __init__(self, schema: type[BaseModel]):
        """
        :param schema: The schema to validate the JSON meta field against.
        """
        super().__init__()

        self.schema = schema

    async def pre_upload(
        self, database: Database, userid: int, content: ContentUpload
    ) -> Optional[str]:
        try:
            self.schema.model_validate(content.meta)
        except ValidationError as e:
            return str(e)
