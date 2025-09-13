import io
from typing import Optional

import numpy as np
import PIL
from databases import Database
from PIL import Image

from immersive_library.models import ContentUpload
from immersive_library.utils import has_tag
from immersive_library.validators.validator import Validator


def get_mask(path: str):
    return np.asarray(Image.open(path).convert("L")) > 0


clothing_mask = get_mask("immersive_library/validators/mca/data/clothing.png")
head_mask = get_mask("immersive_library/validators/mca/data/head.png")

clothing_threshold = 0
hair_threshold = 6


class ValidClothingValidator(Validator):
    async def pre_upload(
        self, database: Database, userid: int, content: ContentUpload
    ) -> Optional[str]:
        try:
            image = Image.open(io.BytesIO(content.payload))
            image = np.array(image.convert("RGBA"))

            if image.shape != (64, 64, 4):
                return "Shape is not (64, 64, 4)!"
        except PIL.UnidentifiedImageError:
            return "Not an valid image!"

    async def post_upload(
        self, database: Database, userid: int, contentid: int
    ) -> Optional[str]:
        """
        Mark skins as invalid if several pixels which are expected to be transparent are not.
        """
        content = await database.fetch_one(
            "SELECT data FROM content WHERE oid=:contentid",
            {"contentid": contentid},
        )

        if content is None:
            return None

        image = Image.open(io.BytesIO(content[0]))
        image = np.array(image.convert("RGBA"))

        clothing_alpha = ((image[:, :, 3] < 128) * clothing_mask).sum()
        head_alpha = (
            ((image[:32, :32, 3] + image[:32, 32:, 3]) < 128) * head_mask[:32, :32]
        ).sum()

        is_hair = await has_tag(database, contentid, "hair")

        seems_invalid = (
            clothing_alpha < clothing_threshold and not is_hair
        ) or head_alpha < hair_threshold

        is_invalid = await has_tag(database, contentid, "invalid")

        if seems_invalid:
            if not is_invalid:
                await database.execute(
                    "INSERT INTO tags (contentid, tag) VALUES(:contentid, :tag)",
                    {"contentid": contentid, "tag": "invalid"},
                )
                return f"{contentid} has been marked as invalid!"
        else:
            if is_invalid:
                return f"{contentid} seems valid but was marked as invalid!"
        return None
