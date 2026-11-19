"""Render the editorial Motion Study layouts and their sample print previews."""

from contextlib import ExitStack
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.filmstrip import FrameBox, GRID_HEIGHT, GRID_WIDTH, print_jpeg
from app.multi_photo import MotionStudyLayout


@dataclass(frozen=True)
class MotionDesign:
    name: str
    description: str
    paper: str
    ink: str
    rule: str
    matte: str


MOTION_DESIGNS = {
    MotionStudyLayout.CONTACT_STACK: MotionDesign(
        "Contact Stack", "Layered, tilted cutouts frame the biggest gesture.",
        "#dce3e9", "#263748", "#8195ab", "#eceff1",
    ),
    MotionStudyLayout.MATCH_CUT: MotionDesign(
        "Match Cut", "Four parallel cuts lead to a wider third frame.",
        "#1b2933", "#eef3f7", "#c3ced6", "#1b2933",
    ),
    MotionStudyLayout.ASCENDING_CUT: MotionDesign(
        "Ascending Cut", "A rising ribbon gives each successive pose more room.",
        "#edf0f2", "#24313e", "#8297aa", "#f5f6f5",
    ),
}

SAMPLE_PATH = Path(__file__).parent / "assets" / "motion-study-sample.jpg"
SAMPLE_SHOTS = {4: (0, 2, 3, 5), 5: (0, 1, 2, 3, 5), 6: (0, 1, 2, 3, 4, 5)}


@dataclass(frozen=True)
class Panel:
    # Geometry is measured in percentages of the 6 × 4 print.
    x: float
    y: float
    width: float
    height: float
    cut: tuple[tuple[float, float], ...] = ()
    angle: int = 0
    layer: int = 0

    def box(self) -> FrameBox:
        x = round(self.x * GRID_WIDTH / 100)
        y = round(self.y * GRID_HEIGHT / 100)
        right = round((self.x + self.width) * GRID_WIDTH / 100)
        bottom = round((self.y + self.height) * GRID_HEIGHT / 100)
        return x, y, right - x, bottom - y


def motion_panels(layout: MotionStudyLayout, count: int) -> list[Panel]:
    if count not in layout.counts:
        raise ValueError("This Motion Study layout does not support that number of photos")

    if layout == MotionStudyLayout.CONTACT_STACK:
        return [
            Panel(8, 24, 32, 48, ((0, 2), (96, 0), (100, 83), (93, 99), (3, 96)), -8, 1),
            Panel(25, 43, 31, 43, ((1, 0), (100, 4), (96, 97), (10, 100), (0, 77)), 5, 3),
            Panel(46, 17, 41, 63, ((4, 1), (96, 0), (100, 95), (72, 100), (0, 96)), -5, 2),
            Panel(72, 41, 23, 45, ((0, 0), (100, 2), (94, 88), (83, 100), (5, 94)), 7, 4),
        ]

    if layout == MotionStudyLayout.MATCH_CUT:
        panels = []
        gutter, slope = .48, .09
        left_at_middle = 8.0
        # Every edge uses the same slope. The gap measured at the middle holds throughout the shared height.
        for y, height, width in ((15.3, 59.4, 17.35), (18.8, 59.3, 18.05), (14.9, 60, 30.4), (19.9, 60, 18.3)):
            lean = slope * height
            bounds = width + lean
            x = left_at_middle + slope * (50 - y - height)
            cut = ((100 * lean / bounds, 0), (100, 0), (100 * width / bounds, 100), (0, 100))
            panels.append(Panel(x, y, bounds, height, cut))
            left_at_middle += width + gutter
        return panels

    panels = []
    gap = -1.3
    weights = [1 + .19 * index for index in range(count)]
    width_per_weight = (90 - (count - 1) * gap) / sum(weights)
    x = 5.0
    for index, weight in enumerate(weights):
        width = weight * width_per_weight
        height = 40 + 23 * index / (count - 1)
        panels.append(Panel(x, 83 - height, width, height))
        x += width + gap
    return panels


def _cut_mask(size: tuple[int, int], cut: tuple[tuple[float, float], ...]) -> Image.Image:
    width, height = size
    if not cut:
        return Image.new("L", size, 255)
    with Image.new("L", (width * 3, height * 3)) as mask:
        vertices = [(round(x * width * 3 / 100), round(y * height * 3 / 100)) for x, y in cut]
        ImageDraw.Draw(mask).polygon(vertices, fill=255)
        return mask.resize(size, Image.Resampling.LANCZOS)


def _place_panel(canvas: Image.Image, source: Path | Image.Image, panel: Panel, layout: MotionStudyLayout) -> None:
    x, y, width, height = panel.box()
    left, top, right, bottom = 0, 0, 0, 0
    if layout == MotionStudyLayout.CONTACT_STACK:
        left = right = round(width * .035)
        top, bottom = round(height * .03), round(height * .05)
    elif layout == MotionStudyLayout.ASCENDING_CUT:
        left = top = right = bottom = 4
    photo_size = width - left - right, height - top - bottom
    with ExitStack() as images:
        if isinstance(source, Path):
            source = images.enter_context(Image.open(source, formats=("JPEG",)))
            ImageOps.exif_transpose(source, in_place=True)
        rgb = images.enter_context(source.convert("RGB"))
        crop = images.enter_context(ImageOps.fit(rgb, photo_size, Image.Resampling.LANCZOS, centering=(.5, .22)))
        tile = images.enter_context(Image.new("RGBA", (width, height), MOTION_DESIGNS[layout].matte))
        inner_cut = panel.cut if layout == MotionStudyLayout.CONTACT_STACK else ()
        inner_mask = images.enter_context(_cut_mask(photo_size, inner_cut))
        tile.paste(crop, (left, top), inner_mask)
        tile.putalpha(images.enter_context(_cut_mask(tile.size, panel.cut)))
        if panel.angle:
            rotated = images.enter_context(tile.rotate(-panel.angle, Image.Resampling.BICUBIC, expand=True))
            canvas.paste(rotated, (x + (width - rotated.width) // 2, y + (height - rotated.height) // 2), rotated)
        else:
            canvas.paste(tile, (x, y), tile)


def _compose(sources: Sequence[Path | Image.Image], layout: MotionStudyLayout, *, preview: bool = False) -> bytes:
    panels = motion_panels(layout, len(sources))
    design = MOTION_DESIGNS[layout]
    with Image.new("RGB", (GRID_WIDTH, GRID_HEIGHT), design.paper) as canvas:
        draw = ImageDraw.Draw(canvas)
        if layout == MotionStudyLayout.MATCH_CUT:
            draw.text((126, 60), "MOTION STUDY", font=ImageFont.load_default(54), fill=design.ink)
            draw.line((126, 145, 1710, 145), fill=design.rule, width=3)
            draw.line((88, 1042, 1719, 1042), fill=design.rule, width=3)
        else:
            title = ImageFont.load_default(47)
            index = ImageFont.load_default(42)
            draw.text((90, 84), "MOTION STUDY", font=title, fill=design.ink)
            draw.text((1710, 84), f"01-{len(sources):02d}", font=index, fill=design.ink, anchor="rt")
            draw.line((90, 168, 1710, 168), fill=design.rule, width=3)
            draw.line((90, 1056, 1710, 1056), fill=design.rule, width=3)
            draw.text((90, 1080), "01", font=index, fill=design.ink)
            draw.text((1672, 1080), f"{len(sources):02d}", font=index, fill=design.ink, anchor="rt")
            draw.line((1683, 1101, 1710, 1101), fill=design.ink, width=3)
            draw.line([(1702, 1094), (1710, 1101), (1702, 1108)], fill=design.ink, width=3)

        for source, panel in sorted(zip(sources, panels, strict=True), key=lambda item: item[1].layer):
            _place_panel(canvas, source, panel, layout)
        if preview:
            with canvas.resize((720, 480), Image.Resampling.LANCZOS) as thumbnail:
                return print_jpeg(thumbnail)
        return print_jpeg(canvas)


def render_motion_study(originals: Sequence[Path], layout: MotionStudyLayout) -> bytes:
    return _compose(originals, layout)


@lru_cache(maxsize=5)
def motion_preview(layout: MotionStudyLayout, count: int) -> bytes:
    with ExitStack() as images:
        sheet = images.enter_context(Image.open(SAMPLE_PATH, formats=("JPEG",)))
        width, height = sheet.width // 3, sheet.height // 2
        sources = []
        for shot in SAMPLE_SHOTS[count]:
            left, top = (shot % 3) * width, (shot // 3) * height
            sources.append(images.enter_context(sheet.crop((left, top, left + width, top + height))))
        return _compose(sources, layout, preview=True)
