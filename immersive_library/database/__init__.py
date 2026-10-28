import os
import sqlite3

from databases import Database
from dotenv import load_dotenv


class Connection(sqlite3.Connection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.execute("pragma journal_mode = DELETE")
        self.execute("pragma synchronous = FULL")
        self.execute("pragma journal_size_limit = 67108864")
        self.execute("pragma mmap_size = 0")
        self.execute("pragma cache_size = 2000")
        self.execute("pragma busy_timeout = 30000")
        self.execute("pragma foreign_keys = ON")


load_dotenv()

database = Database(
    os.getenv("DATABASE_URL", "sqlite:///data/database.db"), factory=Connection
)
