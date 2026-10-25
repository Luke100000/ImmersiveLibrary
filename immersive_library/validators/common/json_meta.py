from databases import Database
from pydantic import BaseModel, ValidationError

from immersive_library.models import ContentUpload
from immersive_library.validators.validator import Validator


class JsonMetaValidator(Validator):
    def __init__(self, schema: type[BaseModel]) -> None:
        """
        :param schema: The schema to validate the JSON meta-field against.
        """
        self.schema = schema

    async def pre_upload(
        self, database: Database, user_id: int, content: ContentUpload
    ) -> str | None:
        try:
            self.schema.model_validate(content.meta)
        except ValidationError as exc:
            return str(exc)
        return None
