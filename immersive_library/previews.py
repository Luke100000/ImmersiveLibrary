from functools import lru_cache
from io import BytesIO

import numpy as np
from PIL import Image, ImageOps

MASTER_SIZE = (1200, 630)
JPEG_QUALITY = 95


@lru_cache(maxsize=3)
def preview_background(size: tuple[int, int]) -> Image.Image:
    width, height = size
    y, x = np.ogrid[:height, :width]

    # Match the page's bottom-centered, farthest-corner elliptical gradient.
    distance = np.sqrt(
        ((x + 0.5 - width / 2) / (width / 2)) ** 2 + ((y + 0.5 - height) / height) ** 2
    ) / np.sqrt(2)
    distance = np.minimum(distance, 1)
    inner = np.array([13, 29, 49])
    outer = np.array([12, 13, 19])
    colors = inner + distance[..., None] * (outer - inner)

    # Dither before 8-bit rounding so the dark gradient does not form color bands.
    noise = np.random.default_rng(0).uniform(-1, 1, (height, width, 1))
    pixels = np.rint(colors + noise).clip(0, 255).astype(np.uint8)
    return Image.fromarray(pixels)


def make_preview(png_bytes: bytes, size: tuple[int, int]) -> bytes:
    with Image.open(BytesIO(png_bytes)) as master:
        foreground = ImageOps.fit(
            master.convert("RGBA"),
            size,
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )

    background = preview_background(size).copy()
    background.paste(foreground, (0, 0), foreground.getchannel("A"))
    output = BytesIO()
    background.save(output, format="JPEG", quality=JPEG_QUALITY, subsampling=0)
    return output.getvalue()
