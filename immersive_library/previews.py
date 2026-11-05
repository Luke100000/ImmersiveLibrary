import math
from functools import lru_cache
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from immersive_library.enums import RenderPreset

MASTER_SIZE = (1200, 630)
JPEG_QUALITY = 95

# The page background, a gradient from a lit bottom center to dark corners.
GRADIENT_INNER = (13, 29, 49)
GRADIENT_OUTER = (12, 13, 19)

# Link previews are flat, since chat apps recompress them into visible blocks.
EMBED_BACKGROUND = (13, 18, 28)

PRESET_SIZES: dict[RenderPreset, tuple[int, int]] = {
    RenderPreset.ICON: (256, 256),
    RenderPreset.THUMBNAIL: (512, 512),
    RenderPreset.EMBED: MASTER_SIZE,
}


@lru_cache(maxsize=2)
def preview_background(size: tuple[int, int]) -> Image.Image:
    width, height = size
    y, x = np.ogrid[:height, :width]

    # Match the page's bottom-centered, farthest-corner elliptical gradient.
    distance = np.sqrt(
        ((x + 0.5 - width / 2) / (width / 2)) ** 2 + ((y + 0.5 - height) / height) ** 2
    ) / np.sqrt(2)
    distance = np.minimum(distance, 1)
    inner = np.array(GRADIENT_INNER)
    outer = np.array(GRADIENT_OUTER)
    colors = inner + distance[..., None] * (outer - inner)

    # Dither before 8-bit rounding so the dark gradient does not form color bands.
    noise = np.random.default_rng(0).uniform(-1, 1, (height, width, 1))
    pixels = np.rint(colors + noise).clip(0, 255).astype(np.uint8)
    return Image.fromarray(pixels)


def compose_preview(png_bytes: bytes, background: Image.Image) -> Image.Image:
    with Image.open(BytesIO(png_bytes)) as master:
        foreground = ImageOps.fit(
            master.convert("RGBA"),
            background.size,
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )

    background = background.copy()
    background.paste(foreground, (0, 0), foreground.getchannel("A"))
    return background


def encode_jpeg(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="JPEG", quality=JPEG_QUALITY, subsampling=0)
    return output.getvalue()


def make_preview(png_bytes: bytes, size: tuple[int, int]) -> bytes:
    if size == MASTER_SIZE:
        background = Image.new("RGB", size, EMBED_BACKGROUND)
    else:
        background = preview_background(size)
    return encode_jpeg(compose_preview(png_bytes, background))


GRID_LIMIT = 8
GRID_GAP = 16
GRID_RADIUS = 16


def grid_layout(count: int) -> tuple[int, int, int]:
    """Columns, rows and tile size that give the largest square tiles."""
    width, height = MASTER_SIZE
    layouts = []
    for rows in range(1, count + 1):
        columns = math.ceil(count / rows)
        tile = min(
            (width - GRID_GAP * (columns + 1)) // columns,
            (height - GRID_GAP * (rows + 1)) // rows,
        )
        layouts.append((columns, rows, tile))
    return max(layouts, key=lambda layout: layout[2])


def make_grid(masters: list[bytes]) -> bytes:
    """Lays out previews like the cards' preview grid, centering a shorter last row."""
    columns, rows, tile = grid_layout(len(masters))
    width, height = MASTER_SIZE
    top = (height - rows * tile - (rows - 1) * GRID_GAP) // 2

    corners = Image.new("L", (tile, tile))
    ImageDraw.Draw(corners).rounded_rectangle(
        (0, 0, tile - 1, tile - 1), GRID_RADIUS, fill=255
    )

    # Darker than the tiles, so they stand out as cards.
    canvas = Image.new("RGB", MASTER_SIZE, GRADIENT_OUTER)
    tile_background = Image.new("RGB", (tile, tile), EMBED_BACKGROUND)
    for row in range(rows):
        row_masters = masters[row * columns : (row + 1) * columns]
        left = (
            width - len(row_masters) * tile - (len(row_masters) - 1) * GRID_GAP
        ) // 2
        y = top + row * (tile + GRID_GAP)
        for column, png_bytes in enumerate(row_masters):
            x = left + column * (tile + GRID_GAP)
            canvas.paste(compose_preview(png_bytes, tile_background), (x, y), corners)
    return encode_jpeg(canvas)
