from typing import Annotated

from pydantic import BaseModel, StringConstraints

from immersive_library.api import app
from immersive_library.common import Project, default_project, projects
from immersive_library.validators.common import (
    MaxSizeValidator,
    ReadOnlyValidator,
    TitleLengthValidator,
)
from immersive_library.validators.common.report import ReportValidator
from immersive_library.validators.mca import (
    InvalidReportValidator,
    ValidClothingValidator,
)

# Block the default project from being uploaded to
default_project.validators.append(ReadOnlyValidator())


class MetaSchema(BaseModel):
    gender: int
    chance: float
    profession: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    exclude: bool
    temperature: float


# Add MCA specific validators
projects["mca"] = Project()
projects["mca"].validators = [
    TitleLengthValidator(),
    MaxSizeValidator(65536),
    ValidClothingValidator(),
    InvalidReportValidator(),
    ReportValidator(lambda reason: reason in ["DEFAULT", "INVALID"]),
]

# Add Immersive Furniture specific validators
projects["furniture"] = Project()
projects["furniture"].validators = [
    TitleLengthValidator(),
    MaxSizeValidator(262144),
]

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app)
