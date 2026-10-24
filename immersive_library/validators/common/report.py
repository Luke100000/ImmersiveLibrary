from collections.abc import Callable

from databases import Database

from immersive_library.validators.validator import Validator


class ReportValidator(Validator):
    def __init__(self, validator: Callable[[str], bool] = lambda reason: True) -> None:
        self.validator = validator

    async def pre_report(
        self, database: Database, userid: int, contentid: int, reason: str
    ) -> str | None:
        if not self.validator(reason):
            return "Reason invalid"
        return None
