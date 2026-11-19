from io import BytesIO

import pytest
from PIL import Image, ImageDraw, ImageOps

from app.time_sculpture import FRAMING_NOTICE, LIGHT_NOTICE, MISSING_NOTICE, POSITION_NOTICE, render_time_sculpture


BACKGROUND = (192, 196, 202)
POSE_COLORS = ((155, 38, 61), (42, 131, 61), (36, 62, 165))


def write_sample(path, *, x=None, color=None, background=BACKGROUND, size=(900, 600)):
    with Image.new("RGB", size, background) as image:
        if x is not None:
            draw = ImageDraw.Draw(image)
            draw.ellipse((x - 29, 137, x + 29, 195), fill=color)
            draw.rounded_rectangle((x - 44, 200, x + 44, 472), radius=18, fill=color)
        image.save(path, "JPEG", quality=94)


@pytest.fixture
def exposures(tmp_path):
    paths = [tmp_path / f"frame-{index}.jpg" for index in range(4)]
    write_sample(paths[0])
    for path, center, color in zip(paths[1:], (150, 450, 750), POSE_COLORS, strict=True):
        write_sample(path, x=center, color=color)
    return paths


def test_sculpture_keeps_all_three_poses_and_clean_seams(exposures):
    before = [path.read_bytes() for path in exposures]
    result = render_time_sculpture(exposures)
    assert result.fallback_reason is None
    with Image.open(BytesIO(result.jpeg)) as image:
        assert image.size == (1800, 1200) and image.info["dpi"] == (300, 300)
        for position, expected in zip((300, 900, 1500), POSE_COLORS, strict=True):
            assert max(abs(first - second) for first, second in zip(image.getpixel((position, 630)), expected)) < 4
        for seam in (599, 600, 1199, 1200):
            assert max(abs(first - second) for first, second in zip(image.getpixel((seam, 630)), BACKGROUND)) < 4
    assert [path.read_bytes() for path in exposures] == before


def test_uniform_brightness_drift_is_matched_at_the_join_and_preserved_in_the_pose(exposures):
    with Image.open(exposures[1]) as source:
        corrected = source.point([min(255, value + 11) for value in range(256)] * 3)
    with corrected:
        corrected.save(exposures[1], "JPEG", quality=94)
    result = render_time_sculpture(exposures)
    assert result.fallback_reason is None
    with Image.open(BytesIO(result.jpeg)) as image, Image.open(exposures[1]) as original:
        with ImageOps.fit(original, image.size, Image.Resampling.LANCZOS) as source:
            for point in ((300, 200), (300, 630)):
                assert max(abs(a - b) for a, b in zip(image.getpixel(point), source.getpixel(point), strict=True)) < 4
        assert max(abs(a - b) for a, b in zip(image.getpixel((550, 200)), BACKGROUND, strict=True)) < 4


def test_local_lighting_drift_does_not_brighten_the_background_near_a_join(exposures):
    with Image.open(exposures[1]) as pose:
        with pose.crop((0, 0, 300, 600)) as left:
            with left.point([min(255, value + 9) for value in range(256)] * 3) as brighter:
                pose.paste(brighter)
        pose.save(exposures[1], "JPEG", quality=94)

    result = render_time_sculpture(exposures)
    assert result.fallback_reason is None
    with Image.open(BytesIO(result.jpeg)) as image:
        for x in (550, 575, 625, 650):
            assert max(abs(a - b) for a, b in zip(image.getpixel((x, 600)), BACKGROUND, strict=True)) < 4
        assert image.getpixel((300, 600))[1] < 65


def test_blend_keeps_low_contrast_detail_next_to_a_pose(exposures):
    with Image.open(exposures[1]) as pose:
        ImageDraw.Draw(pose).rectangle((190, 275, 207, 350), fill=(178, 182, 188))
        pose.save(exposures[1], "JPEG", quality=94)

    result = render_time_sculpture(exposures)
    assert result.fallback_reason is None
    with Image.open(BytesIO(result.jpeg)) as image:
        assert image.getpixel((397, 625))[1] < 187


def test_scene_details_are_preserved_inside_the_exposure_and_in_the_join_correction(exposures):
    with Image.open(exposures[1]) as pose:
        draw = ImageDraw.Draw(pose)
        draw.rectangle((46, 14, 84, 42), fill=(176, 182, 188))
        for x in (260, 265, 270, 275, 280):
            draw.rectangle((x, 94, x + 2, 137), fill=(183, 187, 193))
        pose.save(exposures[1], "JPEG", quality=94)

    result = render_time_sculpture(exposures)
    assert result.fallback_reason is None
    with Image.open(BytesIO(result.jpeg)) as image:
        assert image.getpixel((130, 50))[1] < 186
        assert image.getpixel((558, 230))[1] - image.getpixel((552, 230))[1] > 6


@pytest.mark.parametrize(("sample", "notice"), [
    ({"x": 293, "color": POSE_COLORS[0]}, POSITION_NOTICE),
    ({"x": 150, "color": POSE_COLORS[0], "background": (162, 166, 172)}, LIGHT_NOTICE),
    ({}, MISSING_NOTICE),
    ({"size": (600, 900)}, FRAMING_NOTICE),
])
def test_unreliable_scene_returns_a_printable_pose_sequence(exposures, sample, notice):
    write_sample(exposures[1], **sample)
    result = render_time_sculpture(exposures)
    assert result.fallback_reason == notice
    with Image.open(BytesIO(result.jpeg)) as sequence:
        assert sequence.size == (1800, 1200)
        assert sequence.info["dpi"] == (300, 300)
        assert sequence.getpixel((22, 22))[0] < 40
