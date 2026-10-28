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

MCA_DESCRIPTION_CONTEXT = """Clothing and hair for villagers in Minecraft Comes Alive, a
Minecraft mod. Assets are 64x64 skin overlays in Minecraft's blocky pixel-art style, so
never mention Minecraft, pixels, voxels or blockiness. The preview shows the asset on a
fixed mannequin: a bald, mottled tan body with small yellow eyes. The mannequin is never
part of the asset, so do not mention it or its skin, eyes, bald head or bare limbs, and
do not mistake its mottled texture for clothing. Hair assets cover only the head and
sometimes the shoulders; describe just the hairstyle. The game tints greyscale hair
with each villager's own hair color, so describe grey or white hair by its style, not
its color. Masks, helmets and hoods are headwear, not hair. Profession, gender, chance
and temperature in the metadata only decide which villagers wear the asset."""

FURNITURE_DESCRIPTION_CONTEXT = """Furniture, fixtures, containers, props and decorative
objects built in-game with Immersive Furniture, a Minecraft mod, by arranging shapes
textured with Minecraft blocks and items. Never mention Minecraft, pixels, voxels or
blockiness. Describe the object as a whole rather than how it is assembled, mentioning
individual blocks or items only when they form a visible part such as a cushion,
plant or book. Tags often name the textures used, such as oak_log or glass, which helps
to name visible materials. Particles and sounds are not visible in the preview."""


def register_projects() -> None:
    # Block the default project from being uploaded to
    default_project.validators.append(ReadOnlyValidator())

    # Add MCA specific validators
    projects["mca"] = Project(
        title="MCA Reborn",
        description="Clothing and hair for the villagers of Minecraft Comes Alive Reborn.",
        report_reasons={
            "DEFAULT": "Inappropriate or harmful",
            "INVALID": "Broken or not clothing",
        },
        description_context=MCA_DESCRIPTION_CONTEXT,
    )
    projects["mca"].validators = [
        TitleLengthValidator(),
        MaxSizeValidator(65536),
        ValidClothingValidator(),
        InvalidReportValidator(),
        ReportValidator(lambda reason: reason in ["DEFAULT", "INVALID"]),
    ]

    # Add Immersive Furniture specific validators
    projects["furniture"] = Project(
        title="Immersive Furniture",
        description="Furniture models built in-game with Immersive Furniture.",
        description_context=FURNITURE_DESCRIPTION_CONTEXT,
    )
    projects["furniture"].validators = [
        TitleLengthValidator(),
        MaxSizeValidator(262144),
    ]
