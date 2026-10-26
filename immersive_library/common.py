from fastapi import HTTPException
from starlette.templating import Jinja2Templates

from immersive_library.validators.validator import Validator

templates = Jinja2Templates(directory="templates")


class Project:
    validators: list[Validator]

    def __init__(self, title: str = "", description: str = "") -> None:
        self.title = title
        self.description = description
        self.validators = []

    async def validate(self, callback: str, *args) -> None:
        for validator in self.validators:
            error = await getattr(validator, callback)(*args)
            if error is not None:
                raise HTTPException(400, error)

    async def call(self, callback: str, *args, **kwargs) -> list[str | None]:
        log = []
        for validator in self.validators:
            log.append(await getattr(validator, callback)(*args, **kwargs))
        return log


default_project = Project()

projects: dict[str, Project] = {}


def get_project(name: str) -> Project:
    return projects.get(name, default_project)
