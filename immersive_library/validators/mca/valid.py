import io
from pathlib import Path

import numpy as np
from databases import Database
from PIL import Image

from immersive_library.models import ContentUpload
from immersive_library.utils import has_tag
from immersive_library.validators.validator import Validator

DATA_DIRECTORY = Path(__file__).parent / "data"


def get_mask(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L")) > 0


clothing_mask = get_mask(DATA_DIRECTORY / "clothing.png")
head_mask = get_mask(DATA_DIRECTORY / "head.png")

clothing_threshold = 0
hair_threshold = 6


class ValidClothingValidator(Validator):
    async def pre_upload(
        self, database: Database, user_id: int, content: ContentUpload
    ) -> str | None:
        try:
            with Image.open(io.BytesIO(content.payload)) as image:
                if image.size != (64, 64):
                    return "Shape is not (64, 64, 4)!"

                image.convert("RGBA")
        except (OSError, ValueError, Image.DecompressionBombError):
            return "Not an valid image!"

    async def post_upload(
        self, database: Database, user_id: int, content_id: int
    ) -> str | None:
        """
        Mark skins as invalid if several pixels which are expected to be transparent are not.
        """
        content = await database.fetch_one(
            "SELECT data FROM content WHERE oid=:content_id",
            {"content_id": content_id},
        )

        if content is None:
            return None

        with Image.open(io.BytesIO(content[0])) as image:
            pixels = np.array(image.convert("RGBA"))

        clothing_alpha = ((pixels[:, :, 3] < 128) * clothing_mask).sum()
        head_alpha = (
            ((pixels[:32, :32, 3] + pixels[:32, 32:, 3]) < 128) * head_mask[:32, :32]
        ).sum()

        is_hair = await has_tag(database, content_id, "hair")

        seems_invalid = (
            clothing_alpha < clothing_threshold and not is_hair
        ) or head_alpha < hair_threshold

        if seems_invalid:
            inserted_tag = await database.fetch_val(
                """
                INSERT INTO tags (content_id, tag) VALUES(:content_id, :tag)
                ON CONFLICT (content_id, tag) DO NOTHING RETURNING tag
                """,
                {"content_id": content_id, "tag": "invalid"},
            )
            if inserted_tag is not None:
                return f"{content_id} has been marked as invalid!"
        elif await has_tag(database, content_id, "invalid"):
            return f"{content_id} seems valid but was marked as invalid!"
        return None
