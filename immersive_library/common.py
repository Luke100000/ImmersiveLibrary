from collections.abc import Iterable
from dataclasses import dataclass

from fastapi import HTTPException
from starlette.templating import Jinja2Templates

from immersive_library.validators.validator import Validator

templates = Jinja2Templates(directory="templates")


@dataclass(frozen=True)
class ReportReason:
    name: str
    label: str
    moderator_only: bool = False


DEFAULT_REPORT = ReportReason("DEFAULT", "Inappropriate or harmful")
REVIEWED_REPORT = ReportReason(
    "REVIEWED", "Reviewed by a moderator", moderator_only=True
)


class Project:
    validators: list[Validator]

    def __init__(
        self,
        title: str = "",
        description: str = "",
        report_reasons: Iterable[ReportReason] = (),
        description_context: str | None = None,
    ) -> None:
        self.title = title
        self.description = description
        self.report_reasons = {
            reason.name: reason
            for reason in (DEFAULT_REPORT, *report_reasons, REVIEWED_REPORT)
        }
        # Explains the project's assets and previews to the description model.
        # Assets are only described when it is set.
        self.description_context = description_context
        self.validators = []

    @property
    def public_report_labels(self) -> dict[str, str]:
        return {
            reason.name: reason.label
            for reason in self.report_reasons.values()
            if not reason.moderator_only
        }

    async def validate(self, callback: str, *args) -> None:
        for validator in self.validators:
            error = await getattr(validator, callback)(*args)
            if error is not None:
                raise HTTPException(400, error)

    async def call(self, callback: str, *args, **kwargs) -> list[str | None]:
        return [
            await getattr(validator, callback)(*args, **kwargs)
            for validator in self.validators
        ]


default_project = Project()

projects: dict[str, Project] = {}


def get_project(name: str) -> Project:
    return projects.get(name, default_project)
