"""Lay out and render Signature Strip compositions from ordered original JPEGs."""

from io import BytesIO
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageOps

from app.multi_photo import DEFAULT_PLAN, SignatureStripPlan, StripLayout

FrameBox = tuple[int, int, int, int]
STRIP_WIDTH, STRIP_HEIGHT = 600, 1800
GRID_WIDTH, GRID_HEIGHT = 1800, 1200
GAP = 30
STRIP_MARGIN = 20
GRID_MARGIN = 40


def dimensions(layout: StripLayout) -> tuple[int, int]:
    if layout == StripLayout.GRID:
        return GRID_WIDTH, GRID_HEIGHT
    if layout == StripLayout.HORIZONTAL:
        return STRIP_HEIGHT, STRIP_WIDTH
    return STRIP_WIDTH, STRIP_HEIGHT


def cells(length: int, count: int, margin: int) -> list[tuple[int, int]]:
    available = length - 2 * margin - (count - 1) * GAP
    return [
        (margin + i * GAP + i * available // count, (i + 1) * available // count - i * available // count)
        for i in range(count)
    ]


def frame_boxes(plan: SignatureStripPlan) -> list[FrameBox]:
    if plan.layout == StripLayout.GRID:
        # Two or three images share a single row. A five-shot grid gives two frames a wider crop.
        row_counts = (plan.count,) if plan.count <= 3 else (plan.count // 2, (plan.count + 1) // 2)
        return [
            (x, y, width, height)
            for columns, (y, height) in zip(row_counts, cells(GRID_HEIGHT, len(row_counts), GRID_MARGIN), strict=True)
            for x, width in cells(GRID_WIDTH, columns, GRID_MARGIN)
        ]
    breadth = STRIP_WIDTH - 2 * STRIP_MARGIN
    positions = cells(STRIP_HEIGHT, plan.count, GAP)
    if plan.layout == StripLayout.HORIZONTAL:
        return [(start, STRIP_MARGIN, length, breadth) for start, length in positions]
    return [(STRIP_MARGIN, start, breadth, length) for start, length in positions]


def paste_frame(canvas: Image.Image, path: Path, box: FrameBox, *,
                padding: str = "#ececf1", legacy_crop: bool = False) -> None:
    x, y, width, height = box
    with Image.open(path, formats=("JPEG",)) as image:
        ImageOps.exif_transpose(image, in_place=True)
        with image.convert("RGB") as rgb:
            ratio = (rgb.width / rgb.height) / (width / height)
            if not legacy_crop and min(ratio, 1 / ratio) < 2 / 3:
                with ImageOps.pad(rgb, (width, height), Image.Resampling.LANCZOS, color=padding) as frame:
                    canvas.paste(frame, (x, y))
            else:
                with ImageOps.fit(rgb, (width, height), Image.Resampling.LANCZOS) as frame:
                    canvas.paste(frame, (x, y))


def print_jpeg(canvas: Image.Image) -> bytes:
    with BytesIO() as output:
        canvas.save(output, format="JPEG", quality=94, subsampling=0, dpi=(300, 300))
        return output.getvalue()


def render_filmstrip(originals: Sequence[Path], plan: SignatureStripPlan = DEFAULT_PLAN) -> bytes:
    if len(originals) != plan.count:
        raise ValueError("The number of originals must match the capture plan")
    with Image.new("RGB", dimensions(plan.layout), "white") as canvas:
        for path, box in zip(originals, frame_boxes(plan), strict=True):
            paste_frame(canvas, path, box, legacy_crop=plan == DEFAULT_PLAN)
        return print_jpeg(canvas)
