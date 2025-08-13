from typing import Annotated

from fastapi.requests import Request
from pydantic import BaseModel, StringConstraints
from starlette.responses import HTMLResponse, RedirectResponse

from immersive_library.api import app
from immersive_library.common import default_project, projects, Project, templates
from immersive_library.routers.misc import get_statistics
from immersive_library.validators.common import (
    ReadOnlyValidator,
    TitleLengthValidator,
    MaxSizeValidator,
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
    # JsonMetaValidator(MetaSchema),
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


@app.get("/", response_class=HTMLResponse)
async def get_index():
    return RedirectResponse(url="/mca")


@app.get("/mca", response_class=HTMLResponse)
async def get_front(request: Request):
    return templates.TemplateResponse(
        "statistics.jinja",
        {"request": request, "statistics_data": await get_statistics("mca")},
    )


@app.get("/mca/{contentid}", response_class=HTMLResponse)
async def get_skin_front(request: Request, contentid: int):
    return templates.TemplateResponse(
        "skin.jinja",
        {"request": request, "contentid": contentid},
    )
