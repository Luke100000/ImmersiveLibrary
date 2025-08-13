from typing import Callable

from databases import Database

from immersive_library.validators.validator import Validator


class ReportValidator(Validator):
    def __init__(self, validator: Callable[[str], bool] = lambda x: True):
        super().__init__()

        self.validator = validator

    async def pre_report(
        self, database: Database, userid: int, contentid: int, reason: str
    ):
        if not self.validator(reason):
            return "Reason invalid"
        return None
