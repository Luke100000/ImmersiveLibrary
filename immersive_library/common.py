import os
import sqlite3
from typing import List, Optional

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


database = Database(
    os.getenv("DATABASE_URL", "sqlite:///data/database.db"), factory=Connection
)

templates = Jinja2Templates(directory="templates")


class Project:
    validators: List[Validator]

    def __init__(self):
        self.validators = []

    async def validate(self, callback: str, *args):
        for validator in self.validators:
            exception = await validator.__getattribute__(callback)(*args)
            if exception is not None:
                raise HTTPException(400, exception)

    async def call(self, callback: str, *args, **kwargs) -> List[Optional[str]]:
        log = []
        for validator in self.validators:
            log.append(await validator.__getattribute__(callback)(*args, **kwargs))
        return log


default_project = Project()

projects = {}


def get_project(name: str) -> Project:
    return projects.get(name, default_project)
