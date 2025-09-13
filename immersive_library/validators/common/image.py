import io
from typing import Optional

from databases import Database
from PIL import Image

from immersive_library.models import ContentUpload
from immersive_library.validators.validator import Validator


class ImageValidator(Validator):
    def __init__(
        self,
        width: Optional[int] = None,
        height: Optional[int] = None,
        file_format: str = "png",
        image_mode: str = "RGBA",
    ):
        """
        :param width: The width of the image.
        :param height: The height of the image.
        :param file_format: The file format to convert the image to.
        :param image_mode: The image mode to convert the image to.
        """
        super().__init__()

        self.width = width
        self.height = height
        self.file_format = file_format
        self.image_mode = image_mode

    async def pre_upload(
        self, database: Database, userid: int, content: ContentUpload
    ) -> Optional[str]:
        # noinspection PyBroadException
        try:
            image = Image.open(io.BytesIO(content.payload))

            # Check the image format
            if image.format.lower() != self.file_format.lower():
                return "invalid format"

            # Check image dimensions
            if (
                self.width
                and image.width != self.width
                or image.height
                and image.height != self.height
            ):
                return "invalid dimensions"

            # Strip metadata and save
            output = io.BytesIO()
            image2 = Image.new(self.image_mode, image.size)
            # noinspection PyTypeChecker
            image2.putdata(list(image.getdata()))
            image2.save(output, format=self.file_format)
            output.seek(0)
            content.replace(output.read())

        except Exception:
            return "invalid image"

        return None
