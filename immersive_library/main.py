from immersive_library.api import app
from immersive_library.projects import register_projects

register_projects()

__all__ = ["app"]
