"""Deterministic Pillow treatments for one original JPEG."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from io import BytesIO
from pathlib import Path
from random import Random
from typing import Literal
from uuid import UUID

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageStat

from app.i18n import DEFAULT_LOCALE, Locale, artwork_font, translate

IMAGE_LIMIT = 32 * 1024 * 1024
CLASSIC_SIZE = (1536, 1536)
PRINT_LANDSCAPE = (1800, 1200)
PRINT_PORTRAIT = (1200, 1800)
RESAMPLE = Image.Resampling.LANCZOS
ARTWORK = Path(__file__).with_name("assets")


def classic_filter(jpeg: bytes, _seed: UUID, _locale: Locale = DEFAULT_LOCALE) -> bytes:
    # Preserve the preparation, color grade and JPEG settings of the original local preview.
    with Image.open(BytesIO(jpeg), formats=("JPEG",)) as image, BytesIO() as prepared:
        ImageOps.exif_transpose(image, in_place=True)
        with image.convert("RGB") as rgb:
            rgb.thumbnail(CLASSIC_SIZE, RESAMPLE)
            rgb.info.clear()
            rgb.save(prepared, "JPEG", quality=92)
        prepared.seek(0)
        with Image.open(prepared, formats=("JPEG",)) as source, BytesIO() as output:
            with ImageOps.grayscale(source) as gray, ImageOps.autocontrast(gray) as contrast:
                with ImageOps.colorize(contrast, "#182d40", "#ffdfb4") as tone:
                    with Image.blend(source, tone, .58) as graded:
                        graded.save(output, "JPEG", quality=94)
            return output.getvalue()


def detail_regions(image: Image.Image, tile: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    """Rank distinct crops by tonal variation and texture on a small analysis image."""
    with ImageOps.contain(image, (180, 180), RESAMPLE) as sample:
        with sample.convert("L") as gray, gray.filter(ImageFilter.FIND_EDGES) as edges:
            width, height = sample.size
            ratio = tile[0] / tile[1]
            fraction = .65 if ImageStat.Stat(gray).stddev[0] < 9 else .54
            crop_w = max(1, round(min(width * fraction, height * fraction * ratio)))
            crop_h = max(1, round(min(height, crop_w / ratio)))
            candidates = []
            for x_position in (.1, .35, .65, .9):
                for y_position in (.1, .35, .65, .9):
                    x = round((width - crop_w) * x_position)
                    y = round((height - crop_h) * y_position)
                    box = (x, y, x + crop_w, y + crop_h)
                    with edges.crop(box) as texture, gray.crop(box) as luminance:
                        score = ImageStat.Stat(texture).median[0] + .4 * ImageStat.Stat(luminance).stddev[0]
                    candidates.append((score, box))
    candidates.sort(key=lambda item: item[0], reverse=True)
    first = candidates[0][1]

    def distinct_score(candidate):
        score, box = candidate
        overlap_w = max(0, min(first[2], box[2]) - max(first[0], box[0]))
        overlap_h = max(0, min(first[3], box[3]) - max(first[1], box[1]))
        return score - 160 * overlap_w * overlap_h / (crop_w * crop_h)

    second = max(candidates[1:], key=distinct_score)[1]
    regions = []
    for x0, y0, x1, y1 in (first, second):
        left, top = x0 * image.width // width, y0 * image.height // height
        right = min(image.width, max(left + 1, round(x1 * image.width / width)))
        bottom = min(image.height, max(top + 1, round(y1 * image.height / height)))
        regions.append((left, top, right, bottom))
    return regions


def paste_framed(canvas: Image.Image, source: Image.Image, box: tuple[int, int, int, int], *, crop=False) -> None:
    x, y, width, height = box
    ImageDraw.Draw(canvas).rectangle((x, y, x + width - 1, y + height - 1), fill="#c4c0b4")
    operation = ImageOps.fit if crop else ImageOps.pad
    args = {} if crop else {"color": "#191d21"}
    with operation(source, (width - 4, height - 4), RESAMPLE, **args) as framed:
        canvas.paste(framed, (x + 2, y + 2))


def portrait_atlas(image: Image.Image, _rng: Random, _locale: Locale = DEFAULT_LOCALE) -> Image.Image:
    if image.height > image.width:
        size = PRINT_PORTRAIT
        main = (48, 48, 1104, 1168)
        details = ((48, 1244, 538, 508), (614, 1244, 538, 508))
    else:
        size = PRINT_LANDSCAPE
        main = (48, 48, 1112, 1104)
        details = ((1188, 48, 564, 538), (1188, 614, 564, 538))
    canvas = Image.new("RGB", size, "#e6e0d2")
    paste_framed(canvas, image, main)
    for bounds, placement in zip(detail_regions(image, details[0][2:]), details, strict=True):
        with image.crop(bounds) as detail:
            paste_framed(canvas, detail, placement, crop=True)
    return canvas


def silver_portrait(gray: Image.Image) -> Image.Image:
    with ImageOps.autocontrast(gray, cutoff=1) as contrast:
        with contrast.filter(ImageFilter.UnsharpMask(radius=7, percent=38, threshold=5)) as local:
            with local.point([round(255 * (value / 255) ** .88) for value in range(256)]) as tones:
                return ImageOps.colorize(tones, "#15191e", "#f3ede1", mid="#777779")


def chromatic_relief(image: Image.Image, gray: Image.Image) -> Image.Image:
    # Develop tonal contours at two scales, then offset their color like refracted light.
    with image.resize((1, 1), Image.Resampling.BOX) as swatch:
        sample = swatch.getpixel((0, 0))
    highlight = tuple(round(base * .74 + source * .26) for base, source in zip((219, 237, 251), sample))
    with (gray.filter(ImageFilter.GaussianBlur(2)) as fine,
          gray.filter(ImageFilter.GaussianBlur(9)) as broad,
          ImageChops.difference(gray, fine) as texture,
          ImageChops.difference(fine, broad) as contours,
          ImageChops.lighter(texture, contours) as detail,
          ImageOps.autocontrast(detail, cutoff=2) as levels,
          levels.point([min(176, max(0, value - 38) * 2) for value in range(256)]) as mask,
          ImageOps.autocontrast(gray, cutoff=1) as luminance,
          ImageOps.colorize(luminance, "#111728", highlight, mid="#355472") as tones,
          ImageChops.offset(mask, -4, 1) as warm,
          ImageChops.offset(mask, 5, -1) as cool):
        # The border masks conceal offset wraparound and keep the contour work on the portrait.
        for layer in (warm, cool):
            draw = ImageDraw.Draw(layer)
            draw.rectangle((0, 0, layer.width - 1, layer.height - 1), outline=0, width=7)
        with Image.new("RGB", tones.size, "#d9a983") as amber, Image.new("RGB", tones.size, "#73cae5") as cyan:
            tones.paste(amber, (0, 0), warm)
            tones.paste(cyan, (0, 0), cool)
        return tones.copy()


def parallel_portrait(image: Image.Image, _rng: Random, _locale: Locale = DEFAULT_LOCALE) -> Image.Image:
    canvas = Image.new("RGB", PRINT_LANDSCAPE, "#13171d")
    # Both panels share the same framing. A narrow diagonal splice links the two views.
    size = (870, 1088)
    with (ImageOps.contain(image, size, RESAMPLE) as source, source.convert("L") as gray,
          silver_portrait(gray) as silver, chromatic_relief(source, gray) as relief,
          ImageOps.pad(silver, size, RESAMPLE, color="#22262c") as left,
          ImageOps.pad(relief, size, RESAMPLE, color="#192334") as right,
          Image.new("L", size) as seam):
        canvas.paste(left, (48, 56))
        ImageDraw.Draw(seam).polygon(((30, 0), (869, 0), (869, 1087), (4, 1087)), fill=255)
        canvas.paste(right, (882, 56), seam)
    ImageDraw.Draw(canvas).line(((912, 56), (886, 1143)), fill="#aa9988", width=2)
    return canvas


def film_frame(image: Image.Image, rng: Random, locale: Locale = DEFAULT_LOCALE) -> Image.Image:
    width, height = 1696, 710  # 2.39:1 image window within a 6×4 matte.
    canvas = Image.new("RGB", PRINT_LANDSCAPE, "#171b20")
    with ImageOps.autocontrast(image, cutoff=.6) as contrast, contrast.convert("L") as gray:
        with ImageOps.colorize(gray, "#192534", "#f4e2c7") as grade, Image.blend(contrast, grade, .31) as graded:
            if graded.width / graded.height >= 1.35:
                frame = ImageOps.fit(graded, (width, height), RESAMPLE, centering=(.5, .42))
            else:
                with (ImageOps.fit(graded, (width, height), RESAMPLE) as crop,
                      crop.filter(ImageFilter.GaussianBlur(38)) as surround):
                    frame = ImageEnhance.Brightness(surround).enhance(.58)
                with ImageOps.contain(graded, (width, height), RESAMPLE) as subject:
                    frame.paste(subject, ((width - subject.width) // 2, (height - subject.height) // 2))
            with frame, Image.frombytes("L", (width, height), rng.randbytes(width * height)) as noise:
                with noise.point([125 + value * 7 // 256 for value in range(256)]).convert("RGB") as grain:
                    with ImageChops.add(frame, grain, offset=-128) as still:
                        canvas.paste(still, (52, 211))
    lettering = ImageDraw.Draw(canvas)
    lettering.line(((52, 966), (1747, 966)), fill="#696c69", width=2)
    lettering.text((52, 990), translate("artwork.filmTitle", locale), fill="#e2d8c5", font=artwork_font(locale, 25))
    return canvas


def station_portrait_artwork(source: Image.Image) -> Image.Image:
    # Crop to the station's posts. Fit the outer bevels of the canopy and base
    # to that width while retaining the inner edges and the branding.
    left_edge, left_join, right_join, right_edge = 64, 125, 966, 1024
    with source.crop((0, 20, source.width, 1434)) as trimmed, trimmed.getchannel("A") as alpha:
        artwork = trimmed.crop((left_edge, 0, right_edge, trimmed.height))
        with alpha.point(lambda value: 255 if value >= 245 else 0) as solid:
            for y in range(artwork.height):
                with solid.crop((0, y, trimmed.width, y + 1)) as row:
                    left, _, right, _ = row.getbbox()
                for start, end, offset, width in (
                    (left, left_join, 0, left_join - left_edge),
                    (right_join, right, right_join - left_edge, right_edge - right_join),
                ):
                    with trimmed.crop((start, y, end, y + 1)) as strip:
                        with strip.resize((width, 1), RESAMPLE) as edge:
                            artwork.paste(edge, (offset, y))

    with artwork.getchannel("A") as alpha, alpha.point(lambda value: 255 if value >= 245 else 0) as solid:
        # Keep the source's soft cutout only where it connects to the central opening.
        ImageDraw.floodfill(solid, (artwork.width // 2, artwork.height // 2), 128)
        with solid.point(lambda value: 0 if value == 128 else 255) as outside:
            alpha.paste(255, mask=outside)
            artwork.putalpha(alpha)
    return artwork


def branded_frame(image: Image.Image, _rng: Random, _locale: Locale, *,
                  artwork: str, size: tuple[int, int], flexible_rows: tuple[int, int],
                  prepare: Callable[[Image.Image], Image.Image] | None = None) -> Image.Image:
    width, height = size
    first, last = flexible_rows
    with Image.open(ARTWORK / f"{artwork}.png", formats=("PNG",)) as source, (
        prepare(source) if prepare else source.copy()
    ) as overlay:
        scale = width / overlay.width
        top_height = round(first * scale)
        bottom_height = round((overlay.height - last) * scale)
        # Fit the print by adjusting only the edges alongside the opening. Brand panels scale evenly.
        sections = (
            (0, first, 0, top_height),
            (first, last, top_height, height - top_height - bottom_height),
            (last, overlay.height, height - bottom_height, bottom_height),
        )
        with Image.new("RGBA", size) as frame, Image.new("RGBA", size) as canvas:
            for source_top, source_bottom, target_top, target_height in sections:
                with overlay.crop((0, source_top, overlay.width, source_bottom)) as band:
                    with band.resize((width, target_height), RESAMPLE) as fitted:
                        frame.paste(fitted, (0, target_top))
            left, top, right, bottom = (0, 0, width, height)
            if prepare:
                with frame.getchannel("A") as alpha, ImageChops.invert(alpha) as opening:
                    left, top, right, bottom = opening.getbbox()
            with ImageOps.fit(image, (right - left, bottom - top), RESAMPLE) as photo:
                canvas.paste(photo, (left, top))
            canvas.alpha_composite(frame)
            return canvas.convert("RGB")


def composed(renderer: Callable[[Image.Image, Random, Locale], Image.Image]) -> Callable[[bytes, UUID, Locale], bytes]:
    def from_jpeg(jpeg: bytes, seed: UUID, locale: Locale) -> bytes:
        with Image.open(BytesIO(jpeg), formats=("JPEG",)) as source, BytesIO() as output:
            ImageOps.exif_transpose(source, in_place=True)
            with source.convert("RGB") as rgb:
                rgb.thumbnail((3000, 3000), RESAMPLE)
                with renderer(rgb, Random(seed.int), locale) as composition:
                    composition.save(output, "JPEG", quality=94, subsampling=0, dpi=(300, 300))
            return output.getvalue()
    return from_jpeg


@dataclass(frozen=True)
class Treatment:
    name: str
    description: str
    renderer: Callable[[bytes, UUID, Locale], bytes]
    version: int = 1
    category: Literal["treatment", "frame"] = "treatment"


CATALOG = {
    "portrait-atlas": Treatment("Portrait Atlas", "An editorial portrait with two details from your photo.",
                                composed(portrait_atlas)),
    "parallel-portrait": Treatment("Parallel Portrait", "Silver tones meet color relief in a paired portrait.",
                                   composed(parallel_portrait)),
    "film-frame": Treatment("The Film Frame", "A widescreen still with film grain and a clean matte.",
                            composed(film_frame)),
    "classic-filter": Treatment("Classic Filter", "Warm highlights and cool shadows for a film-style finish.",
                                classic_filter),
}

for artwork, size, flexible_rows, prepare, version in (
    ("hazar-station-portrait", PRINT_PORTRAIT, (697, 1080), station_portrait_artwork, 3),
    ("hazar-station-landscape", PRINT_LANDSCAPE, (250, 555), None, 1),
    ("hazar-travel-portrait", PRINT_PORTRAIT, (663, 841), None, 1),
    ("hazar-travel-landscape", PRINT_LANDSCAPE, (470, 581), None, 1),
    ("hazar-roadside-landscape", PRINT_LANDSCAPE, (280, 545), None, 1),
):
    key = f"studio.treatment.{artwork}"
    CATALOG[artwork] = Treatment(
        name=translate(f"{key}.name"),
        description=translate(f"{key}.description"),
        renderer=composed(partial(branded_frame, artwork=artwork, size=size, flexible_rows=flexible_rows,
                                  prepare=prepare)),
        version=version,
        category="frame",
    )


def render(treatment: str, version: int, jpeg: bytes, original_id: UUID, locale: Locale = DEFAULT_LOCALE) -> bytes:
    recipe = CATALOG[treatment]
    if recipe.version != version:
        raise ValueError("This treatment version is unavailable")
    return recipe.renderer(jpeg, original_id, locale)
