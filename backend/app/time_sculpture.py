"""Fixed-camera, local compositing for three separated poses in one scene."""

from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat

from app.filmstrip import GRID_HEIGHT, GRID_WIDTH, cells, paste_frame, print_jpeg
from app.i18n import DEFAULT_LOCALE, Locale, artwork_font, translate
from app.multi_photo import SCULPTURE_POSITIONS

ANALYSIS_SIZE = (360, 240)
FEATHER = 9
CHANGE_LEVEL = 26
MAX_BACKGROUND_CORRECTION = 12
POSE_PADDING = 5
JOIN_MATCH_RADIUS = 3 * FEATHER
FRAMING_NOTICE = "The frames used different framing. Keep the camera fixed in landscape orientation."
LIGHT_NOTICE = "The background changed between shots. Keep the camera fixed and the lighting steady."
POSITION_NOTICE = "A pose or shadow crossed the marked area. Keep each pose and its shadow inside one area."
MISSING_NOTICE = "A pose was hard to distinguish from the background. Use a clear background and visible contrast."


@dataclass(frozen=True)
class SculptureResult:
    jpeg: bytes
    fallback_reason: str | None = None


def background_offset(plate: Image.Image, pose: Image.Image, index: int) -> tuple[int, int, int]:
    """Match a small color offset only when both unoccupied areas agree."""
    width, height = ANALYSIS_SIZE
    zone = width // 3
    with ImageChops.subtract(plate, pose, offset=128) as signed:
        medians = []
        for position in range(3):
            if position != index:
                with signed.crop((position * zone, 4, (position + 1) * zone, height - 4)) as region:
                    medians.append([round(value - 128) for value in ImageStat.Stat(region).median])
    first, second = medians
    if (max(abs(value) for value in first + second) > MAX_BACKGROUND_CORRECTION or
            max(abs(a - b) for a, b in zip(first, second, strict=True)) > 3):
        return (0, 0, 0)
    return (round((first[0] + second[0]) / 2), round((first[1] + second[1]) / 2), round((first[2] + second[2]) / 2))


def apply_offset(image: Image.Image, offsets: tuple[int, int, int]) -> Image.Image:
    return image.point([max(0, min(255, value + offset)) for offset in offsets for value in range(256)])


def difference_strength(plate: Image.Image, pose: Image.Image) -> Image.Image:
    with ExitStack() as images:
        rgb_delta = images.enter_context(ImageChops.difference(plate, pose))
        red, green, blue = (images.enter_context(channel) for channel in rgb_delta.split())
        rg = images.enter_context(ImageChops.lighter(red, green))
        return ImageChops.lighter(rg, blue)


def safe_bounds(index: int) -> tuple[int, int, int, int]:
    width, height = ANALYSIS_SIZE
    zone = width // 3
    return (index * zone + FEATHER, 4, (index + 1) * zone - FEATHER, height - 4)


def zone_validation(delta: Image.Image, changes: Image.Image, index: int) -> str | None:
    width, height = ANALYSIS_SIZE
    safe_area = safe_bounds(index)
    left, _, right, _ = safe_area
    with changes.crop(safe_area) as safe:
        inside = safe.histogram()[255]
    outside = changes.histogram()[255] - inside

    for bounds in ((0, 0, left, height), (right, 0, width, height)):
        with delta.crop(bounds) as region:
            if ImageStat.Stat(region).mean[0] > 9:
                return LIGHT_NOTICE
    if outside > min(345, max(80, inside * .12)):
        return POSITION_NOTICE
    if inside < 475:
        return MISSING_NOTICE
    return None


def pose_protection(changes: Image.Image, index: int) -> Image.Image:
    safe_area = safe_bounds(index)
    left, top, _, _ = safe_area
    with changes.crop(safe_area) as area, Image.new("L", ANALYSIS_SIZE) as envelope:
        draw = ImageDraw.Draw(envelope)
        # Span each band of the pose so fine details between detected edges keep their original tones.
        for start in range(0, area.height, POSE_PADDING):
            stop = min(start + POSE_PADDING, area.height)
            with area.crop((0, start, area.width, stop)) as band:
                box = band.getbbox()
            if box is not None:
                draw.rectangle((left + box[0], top + start, left + box[2] - 1, top + stop - 1), fill=255)
        return envelope.filter(ImageFilter.MaxFilter(2 * POSE_PADDING + 1))


def join_mask(size: tuple[int, int], index: int, fade_width: int, *, near_join: bool = False) -> Image.Image:
    width, _ = size
    zone = width // 3
    left, right = index * zone, (index + 1) * zone
    opacity = bytearray(width)
    for x in range(left, right):
        distance = min(x - left if index > 0 else fade_width, right - 1 - x if index < 2 else fade_width)
        if near_join:
            # Match color throughout the feather, then taper the correction into the original exposure.
            progress = min(1, max(0, distance - FEATHER) / (fade_width - FEATHER))
        else:
            progress = min(1, distance / fade_width)
        interior = round(255 * progress * progress * (3 - 2 * progress))
        opacity[x] = 255 - interior if near_join else interior
    with Image.frombytes("L", (width, 1), bytes(opacity)) as ramp:
        return ramp.resize(size, Image.Resampling.NEAREST)


def balance_join_tones(reference: Image.Image, sample: Image.Image, pose: Image.Image,
                       index: int, protected: Image.Image) -> Image.Image:
    with ExitStack() as images:
        # The reference fills the pose only in the color estimator. The output starts with the posed exposure.
        background = images.enter_context(Image.composite(reference, sample, protected))
        reference_color = images.enter_context(reference.filter(ImageFilter.GaussianBlur(4)))
        background_color = images.enter_context(background.filter(ImageFilter.GaussianBlur(4)))
        delta = images.enter_context(ImageChops.subtract(reference_color, background_color, offset=128))
        limit = MAX_BACKGROUND_CORRECTION
        bounded = images.enter_context(delta.point([max(128 - limit, min(128 + limit, value))
                                                     for value in range(256)] * 3))
        soft = images.enter_context(protected.filter(ImageFilter.GaussianBlur(3)))
        protection = images.enter_context(ImageChops.lighter(protected, soft))
        available = images.enter_context(ImageChops.invert(protection))
        join = images.enter_context(join_mask(ANALYSIS_SIZE, index, JOIN_MATCH_RADIUS, near_join=True))
        strength = images.enter_context(ImageChops.multiply(join, available))
        neutral = images.enter_context(Image.new("RGB", ANALYSIS_SIZE, (128, 128, 128)))
        adjustment = images.enter_context(Image.composite(bounded, neutral, strength))
        full = images.enter_context(adjustment.resize(pose.size, Image.Resampling.BILINEAR))
        return ImageChops.add(pose, full, offset=-128)


def pose_sequence(originals: Sequence[Path], reason: str, locale: Locale = DEFAULT_LOCALE) -> SculptureResult:
    with Image.new("RGB", (GRID_WIDTH, GRID_HEIGHT), "#172233") as canvas:
        draw = ImageDraw.Draw(canvas)
        draw.text((86, 89), translate("artwork.poseSequence", locale), font=artwork_font(locale, 70), fill="#eef3f9")
        draw.line((86, 195, 1714, 195), fill="#a4bddd", width=2)
        caption = artwork_font(locale, 27)
        for path, position, (x, width) in zip(originals, SCULPTURE_POSITIONS, cells(GRID_WIDTH, 3, 86), strict=True):
            paste_frame(canvas, path, (x, 240, width, 750), padding="#25354a")
            draw.text((x, 1016), translate(f"studio.positions.{position.lower()}", locale), font=caption, fill="#eef3f9")
        return SculptureResult(print_jpeg(canvas), reason)


def render_time_sculpture(originals: Sequence[Path], locale: Locale = DEFAULT_LOCALE) -> SculptureResult:
    if len(originals) != 4:
        raise ValueError("Time Sculpture requires an empty scene and three poses")
    with ExitStack() as frames:
        normalized: list[Image.Image] = []
        source_size: tuple[int, int] | None = None
        for path in originals:
            with Image.open(path, formats=("JPEG",)) as original:
                ImageOps.exif_transpose(original, in_place=True)
                if not 1.42 <= original.width / original.height <= 1.58 or source_size not in (None, original.size):
                    return pose_sequence(originals[1:], FRAMING_NOTICE, locale)
                source_size = original.size
                with original.convert("RGB") as rgb:
                    normalized.append(frames.enter_context(ImageOps.fit(
                        rgb, (GRID_WIDTH, GRID_HEIGHT), Image.Resampling.LANCZOS,
                    )))

        plate, *poses = normalized
        samples = [frames.enter_context(frame.resize(ANALYSIS_SIZE, Image.Resampling.BOX)) for frame in normalized]
        protected_areas = []
        for index, sample in enumerate(samples[1:]):
            offset = background_offset(samples[0], sample, index)
            corrected = frames.enter_context(apply_offset(sample, offset)) if any(offset) else sample
            with (
                difference_strength(samples[0], corrected) as delta,
                delta.point([0] * CHANGE_LEVEL + [255] * (256 - CHANGE_LEVEL)) as thresholded,
                thresholded.filter(ImageFilter.MedianFilter(3)) as changes,
            ):
                reason = zone_validation(delta, changes, index)
                if reason is not None:
                    return pose_sequence(originals[1:], reason, locale)
                protected_areas.append(frames.enter_context(pose_protection(changes, index)))

        with plate.copy() as result:
            feather = GRID_WIDTH * FEATHER // ANALYSIS_SIZE[0]
            for index, (pose, sample, protected) in enumerate(zip(poses, samples[1:], protected_areas, strict=True)):
                with (
                    balance_join_tones(samples[0], sample, pose, index, protected) as source,
                    join_mask(pose.size, index, feather) as mask,
                ):
                    result.paste(source, mask=mask)
            return SculptureResult(print_jpeg(result))
