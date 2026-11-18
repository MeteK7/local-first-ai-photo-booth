"""Render the booth's three-frame Classic filmstrip from its original JPEGs."""

from io import BytesIO
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageOps

FRAME_COUNT = 3
FRAME_SIZE = 560
LEFT_MARGIN = 20
GAP = 30
WIDTH = FRAME_SIZE + 2 * LEFT_MARGIN
HEIGHT = FRAME_COUNT * FRAME_SIZE + (FRAME_COUNT + 1) * GAP


def render_filmstrip(originals: Sequence[Path]) -> bytes:
    if len(originals) != FRAME_COUNT:
        raise ValueError("A filmstrip needs exactly three originals")
    with BytesIO() as output, Image.new("RGB", (WIDTH, HEIGHT), "white") as canvas:
        for index, path in enumerate(originals):
            with Image.open(path, formats=("JPEG",)) as image:
                ImageOps.exif_transpose(image, in_place=True)
                with image.convert("RGB") as rgb:
                    with ImageOps.fit(rgb, (FRAME_SIZE, FRAME_SIZE), Image.Resampling.LANCZOS) as frame:
                        canvas.paste(frame, (LEFT_MARGIN, GAP + index * (FRAME_SIZE + GAP)))
        canvas.save(output, format="JPEG", quality=94, subsampling=0, dpi=(300, 300))
        return output.getvalue()
