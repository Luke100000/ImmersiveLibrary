import io

import numpy as np
from databases import Database
from PIL import Image

from immersive_library.models import ContentUpload
from immersive_library.utils import has_tag
from immersive_library.validators.validator import Validator


def get_mask(path: str):
    with Image.open(path) as image:
        return np.asarray(image.convert("L")) > 0


clothing_mask = get_mask("immersive_library/validators/mca/data/clothing.png")
head_mask = get_mask("immersive_library/validators/mca/data/head.png")

clothing_threshold = 0
hair_threshold = 6


class ValidClothingValidator(Validator):
    async def pre_upload(
        self, database: Database, userid: int, content: ContentUpload
    ) -> str | None:
        try:
            with Image.open(io.BytesIO(content.payload)) as image:
                if image.size != (64, 64):
                    return "Shape is not (64, 64, 4)!"

                image.convert("RGBA")
        except (OSError, ValueError, Image.DecompressionBombError):
            return "Not an valid image!"

    async def post_upload(
        self, database: Database, userid: int, contentid: int
    ) -> str | None:
        """
        Mark skins as invalid if several pixels which are expected to be transparent are not.
        """
        content = await database.fetch_one(
            "SELECT data FROM content WHERE oid=:contentid",
            {"contentid": contentid},
        )

        if content is None:
            return None

        with Image.open(io.BytesIO(content[0])) as image:
            pixels = np.array(image.convert("RGBA"))

        clothing_alpha = ((pixels[:, :, 3] < 128) * clothing_mask).sum()
        head_alpha = (
            ((pixels[:32, :32, 3] + pixels[:32, 32:, 3]) < 128) * head_mask[:32, :32]
        ).sum()

        is_hair = await has_tag(database, contentid, "hair")

        seems_invalid = (
            clothing_alpha < clothing_threshold and not is_hair
        ) or head_alpha < hair_threshold

        if seems_invalid:
            inserted_tag = await database.fetch_val(
                """
                INSERT INTO tags (contentid, tag) VALUES(:contentid, :tag)
                ON CONFLICT (contentid, tag) DO NOTHING RETURNING tag
                """,
                {"contentid": contentid, "tag": "invalid"},
            )
            if inserted_tag is not None:
                return f"{contentid} has been marked as invalid!"
        elif await has_tag(database, contentid, "invalid"):
            return f"{contentid} seems valid but was marked as invalid!"
        return None
