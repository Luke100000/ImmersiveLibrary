import os
import sqlite3

from databases import Database
from fastapi import HTTPException
from starlette.templating import Jinja2Templates

from immersive_library.validators.validator import Validator


class Connection(sqlite3.Connection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.execute("pragma journal_mode = DELETE")
        self.execute("pragma synchronous = FULL")
        self.execute("pragma journal_size_limit = 67108864")
        self.execute("pragma mmap_size = 0")
        self.execute("pragma cache_size = 2000")
        self.execute("pragma busy_timeout = 5000")
        self.execute("pragma foreign_keys = ON")


database = Database(
    os.getenv("DATABASE_URL", "sqlite:///data/database.db"), factory=Connection
)

templates = Jinja2Templates(directory="templates")


class Project:
    validators: list[Validator]

    def __init__(self) -> None:
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
