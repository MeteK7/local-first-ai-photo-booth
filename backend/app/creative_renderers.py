"""Deterministic Pillow treatments for one original JPEG."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache, partial
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
NEW_YEAR_PHOTO_BOXES = {
    "new-year-bright-blue-landscape": (626, 122, 1421, 711),
    "new-year-vibrant-2027-landscape": (624, 117, 1426, 718),
    "new-year-cozy-winter-landscape": (716, 156, 1456, 884),
    "new-year-pine-cones-portrait": (120, 339, 809, 1134),
    "new-year-fireworks-portrait": (0, 0, 1024, 1536),
    "new-year-colorful-2027-portrait": (0, 0, 1023, 1538),
}


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


def station_portrait_layers(source: Image.Image) -> tuple[Image.Image, Image.Image]:
    with source.getchannel("A") as alpha, alpha.point(
        lambda value: 255 if value >= 230 else 0,
    ) as opaque:
        with opaque.filter(ImageFilter.MedianFilter(5)) as silhouette:
            # Find the enclosed photo window using the original inner contour.
            ImageDraw.floodfill(silhouette, (source.width // 2, source.height // 2), 128)
            with silhouette.point(lambda value: 255 if value == 128 else 0) as interior:
                opening = interior.filter(ImageFilter.MaxFilter(7))
            # Keep the real edge's antialiasing and drop stray alpha beyond it.
            with silhouette.point(lambda value: 255 if value else 0) as footprint:
                with footprint.filter(ImageFilter.MaxFilter(5)) as supported:
                    artwork = source.copy()
                    with ImageChops.multiply(alpha, supported) as cleaned:
                        artwork.putalpha(cleaned)
    return artwork, opening


def station_portrait(image: Image.Image, _rng: Random, _locale: Locale) -> Image.Image:
    with Image.open(ARTWORK / "hazar-station-portrait.png", formats=("PNG",)) as source:
        artwork, opening = station_portrait_layers(source)
    with artwork, opening:
        bounds = artwork.getbbox(alpha_only=True)
        left, top, right, bottom = opening.getbbox()
        with (Image.new("RGBA", artwork.size, "white") as panel,
              ImageOps.fit(image, (right - left, bottom - top), RESAMPLE) as photo,
              opening.crop((left, top, right, bottom)) as aperture):
            panel.paste(photo, (left, top), aperture)
            panel.alpha_composite(artwork)
            # Trim the empty perimeter at native resolution, retaining every
            # visible pixel and letting the printer fit the result to the paper.
            with panel.crop(bounds) as trimmed:
                return trimmed.convert("RGB")


def branded_frame(image: Image.Image, _rng: Random, _locale: Locale, *,
                  artwork: str, size: tuple[int, int], flexible_rows: tuple[int, int]) -> Image.Image:
    width, height = size
    first, last = flexible_rows
    with Image.open(ARTWORK / f"{artwork}.png", formats=("PNG",)) as overlay:
        scale = width / overlay.width
        top_height = round(first * scale)
        bottom_height = round((overlay.height - last) * scale)
        # Fit the print by adjusting only the edges alongside the opening. Brand panels scale evenly.
        sections = (
            (0, first, 0, top_height),
            (first, last, top_height, height - top_height - bottom_height),
            (last, overlay.height, height - bottom_height, bottom_height),
        )
        with ImageOps.fit(image, size, RESAMPLE) as photo, photo.convert("RGBA") as canvas:
            for source_top, source_bottom, target_top, target_height in sections:
                with overlay.crop((0, source_top, overlay.width, source_bottom)) as band:
                    with band.resize((width, target_height), RESAMPLE) as fitted:
                        canvas.alpha_composite(fitted, (0, target_top))
            return canvas.convert("RGB")


def place_photo_in_black_opening(artwork: Image.Image, photo: Image.Image) -> Image.Image:
    red, green, blue = artwork.split()
    with red, green, blue, ImageChops.lighter(red, green) as warm:
        with ImageChops.lighter(warm, blue) as peak, peak.point(lambda value: 0 if value <= 12 else 255) as edges:
            # Key only the dark region connected to the center. The night sky
            # and the dark details in the artwork keep their original colors.
            ImageDraw.floodfill(edges, (artwork.width // 2, artwork.height // 2), 128)
            with (edges.point(lambda value: 255 if value == 128 else 0) as opening,
                  opening.filter(ImageFilter.MaxFilter(9)) as bleed,
                  bleed.filter(ImageFilter.GaussianBlur(2)) as feather,
                  peak.point(lambda value: min(255, max(0, (48 - value) * 255 // 44))) as transmission,
                  ImageChops.multiply(feather, transmission) as mask,
                  Image.new("RGB", artwork.size) as black,
                  Image.composite(photo, black, mask) as visible_photo):
                # The supplied RGB art already includes the glow against black.
                return ImageChops.add(artwork, visible_photo)


def new_year_frame(image: Image.Image, _rng: Random, _locale: Locale, *, artwork: str) -> Image.Image:
    with Image.open(ARTWORK / f"{artwork}.png", formats=("PNG",)) as overlay:
        if box := NEW_YEAR_PHOTO_BOXES.get(artwork):
            left, top, right, bottom = box
            # Center the subject in the off-center aperture rather than behind the greeting.
            with (Image.new("RGBA", overlay.size, "white") as background,
                  ImageOps.fit(image, (right - left, bottom - top), RESAMPLE, centering=(.5, .35)) as photo):
                background.paste(photo, (left, top))
                background.alpha_composite(overlay)
                return background.convert("RGB")
        # Keep headroom from the source when fitting a wide layout with a decorated header.
        with ImageOps.fit(image, overlay.size, RESAMPLE, centering=(.5, 0)) as photo:
            if overlay.mode == "RGBA":
                with photo.convert("RGBA") as background, Image.alpha_composite(background, overlay) as result:
                    return result.convert("RGB")
            return place_photo_in_black_opening(overlay, photo)


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


TreatmentCategory = Literal["treatment", "frame", "new-year-frame"]


@dataclass(frozen=True)
class Treatment:
    name: str
    description: str
    renderer: Callable[[bytes, UUID, Locale], bytes]
    version: int = 1
    category: TreatmentCategory = "treatment"
    frame_size: tuple[int, int] | None = None


CATALOG = {
    "portrait-atlas": Treatment("Portrait Atlas", "An editorial portrait with two details from your photo.",
                                composed(portrait_atlas)),
    "parallel-portrait": Treatment("Parallel Portrait", "Silver tones meet color relief in a paired portrait.",
                                   composed(parallel_portrait)),
    "film-frame": Treatment("The Film Frame", "A widescreen still with film grain and a clean matte.",
                            composed(film_frame)),
    "classic-filter": Treatment("Classic Filter", "Warm highlights and cool shadows for a film-style finish.",
                                classic_filter),
    "hazar-station-portrait": Treatment(
        name=translate("studio.treatment.hazar-station-portrait.name"),
        description=translate("studio.treatment.hazar-station-portrait.description"),
        renderer=composed(station_portrait),
        version=5,
        category="frame",
        frame_size=(1056, 1429),
    ),
}

for artwork, size, flexible_rows in (
    ("hazar-station-landscape", PRINT_LANDSCAPE, (250, 555)),
    ("hazar-travel-portrait", PRINT_PORTRAIT, (663, 841)),
    ("hazar-travel-landscape", PRINT_LANDSCAPE, (470, 581)),
    ("hazar-roadside-landscape", PRINT_LANDSCAPE, (280, 545)),
):
    key = f"studio.treatment.{artwork}"
    CATALOG[artwork] = Treatment(
        name=translate(f"{key}.name"),
        description=translate(f"{key}.description"),
        renderer=composed(partial(branded_frame, artwork=artwork, size=size, flexible_rows=flexible_rows)),
        category="frame",
        frame_size=size,
    )

for artwork in (
    "new-year-golden-midnight-portrait",
    "new-year-ornate-2027-portrait",
    "new-year-winter-garland-landscape",
    "new-year-winter-drive-blue-landscape",
    "new-year-winter-drive-red-landscape",
    *NEW_YEAR_PHOTO_BOXES,
):
    key = f"studio.treatment.{artwork}"
    with Image.open(ARTWORK / f"{artwork}.png", formats=("PNG",)) as overlay:
        size = overlay.size
    CATALOG[artwork] = Treatment(
        name=translate(f"{key}.name"),
        description=translate(f"{key}.description"),
        renderer=composed(partial(new_year_frame, artwork=artwork)),
        version=2 if artwork in {"new-year-cozy-winter-landscape", "new-year-fireworks-portrait"} else 1,
        category="new-year-frame",
        frame_size=size,
    )


def render(treatment: str, version: int, jpeg: bytes, original_id: UUID, locale: Locale = DEFAULT_LOCALE) -> bytes:
    recipe = CATALOG[treatment]
    if recipe.version != version:
        raise ValueError("This treatment version is unavailable")
    return recipe.renderer(jpeg, original_id, locale)


def frame_preview_size(treatment: str) -> tuple[int, int]:
    size = CATALOG[treatment].frame_size
    if size is None:
        raise ValueError("Only frames have sample previews")
    scale = 360 / max(size)
    return tuple(round(value * scale) for value in size)


@lru_cache(maxsize=32)
def frame_preview(treatment: str) -> bytes:
    """Show the production frame on an offline sample, never a customer's photo."""
    size = frame_preview_size(treatment)
    recipe = CATALOG[treatment]
    with Image.open(ARTWORK / "motion-study-sample.jpg") as sample, \
            sample.crop((0, 0, sample.width // 3, sample.height // 2)) as portrait, BytesIO() as source:
        # The Hazar brand panels surround a smaller aperture. Position the
        # demonstration portrait inside that aperture so its face stays visible.
        top = round(portrait.height * (.7 if size[0] < size[1] else .55)) if recipe.category == "frame" else 0
        with ImageOps.expand(portrait, border=(0, top, 0, 0), fill=portrait.getpixel((0, 0))) as prepared:
            prepared.save(source, "JPEG", quality=94)
        rendered = render(treatment, recipe.version, source.getvalue(), UUID(int=0))
    with Image.open(BytesIO(rendered)) as composition, composition.resize(size, RESAMPLE) as thumbnail, \
            BytesIO() as output:
        thumbnail.save(output, "JPEG", quality=88, subsampling=0)
        return output.getvalue()
