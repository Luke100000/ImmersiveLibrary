from typing import Annotated

from fastapi.requests import Request
from pydantic import BaseModel, StringConstraints
from starlette.responses import HTMLResponse

from immersive_library.api import (
    app,
    templates,
    get_statistics,
    projects,
    Project,
    default_project,
)
from immersive_library.validators.common import (
    ReadOnlyValidator,
    TitleLengthValidator,
    MaxSizeValidator,
    JsonMetaValidator,
)
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
    JsonMetaValidator(MetaSchema),
    ValidClothingValidator(),
    InvalidReportValidator(),
]

# Add Immersive Furniture specific validators
projects["furniture"] = Project()
projects["furniture"].validators = [
    TitleLengthValidator(),
    MaxSizeValidator(262144),
]


@app.get("/", response_class=HTMLResponse)
async def get_front(request: Request):
    return templates.TemplateResponse(
        "statistics.jinja",
        {"request": request, "statistics_data": await get_statistics()},
    )
