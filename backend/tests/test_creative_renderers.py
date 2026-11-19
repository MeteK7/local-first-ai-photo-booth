from hashlib import sha256
from io import BytesIO
from uuid import UUID

import pytest
from PIL import Image, ImageChops, ImageDraw

from app.creative_renderers import CATALOG, detail_regions, render

SEED = UUID(int=12)


def sample(size, *, orientation=None, textured=True):
    with Image.new("RGB", size, "#2d414d") as image, BytesIO() as buffer:
        w, h = size
        if textured:
            draw = ImageDraw.Draw(image)
            draw.ellipse((w // 4, h // 12, w * 3 // 4, h - 2), fill="#d6aa81")
            draw.rectangle((w // 18, h // 8, w // 3, h // 3), fill="#24abd1")
            draw.line((5, h - 5, w - 5, 5), fill="#334844", width=6)
        exif = image.getexif()
        exif[270] = "Private fixture metadata"
        if orientation:
            exif[274] = orientation
        image.save(buffer, "JPEG", exif=exif)
        return buffer.getvalue()


def test_classic_filter_matches_prior_preview_bytes():
    with Image.new("RGB", (480, 320), "#2d414d") as source, BytesIO() as output:
        draw = ImageDraw.Draw(source)
        draw.ellipse((104, 30, 360, 318), fill="#d6aa81")
        draw.rectangle((27, 39, 170, 120), fill="#24abd1")
        draw.line((5, 300, 410, 5), fill="#334844", width=7)
        exif = source.getexif()
        exif[274] = 6
        exif[270] = "Private test metadata"
        source.save(output, format="JPEG", exif=exif)
        result = render("classic-filter", 1, output.getvalue(), SEED)
    assert sha256(result).hexdigest() == "636612c8ad877522170ed334398f74500a86d176fca3a6397d728c7757d9c524"
    with Image.open(BytesIO(result)) as image:
        assert image.size == (320, 480)
        assert not image.getexif()


@pytest.mark.parametrize(("size", "orientation", "portrait"), [
    ((540, 360), None, False), ((350, 620), None, True), ((640, 400), 8, True), ((24, 24), None, False),
])
def test_compositions_fit_photo_paper_and_strip_camera_metadata(size, orientation, portrait):
    original = sample(size, orientation=orientation, textured=size != (24, 24))
    variants = [render(name, 1, original, SEED) for name in CATALOG]
    assert len(set(variants)) == 4
    for name, jpeg in zip(CATALOG, variants, strict=True):
        with Image.open(BytesIO(jpeg)) as image:
            image.load()
            assert image.mode == "RGB"
            assert not image.getexif()
            if name != "classic-filter":
                expected = (1200, 1800) if portrait and name == "portrait-atlas" else (1800, 1200)
                assert image.size == expected and image.info["dpi"] == (300, 300)


def test_detail_crops_are_distinct_and_inside_original():
    with Image.open(BytesIO(sample((301, 506)))) as image:
        boxes = detail_regions(image, (538, 508))
        assert len(set(boxes)) == 2
        assert all(0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height for x0, y0, x1, y1 in boxes)


def test_parallel_changes_real_detail_and_film_grain_is_repeatable():
    original = sample((320, 480))
    parallel = render("parallel-portrait", 1, original, SEED)
    with Image.open(BytesIO(parallel)) as image:
        with image.crop((68, 200, 848, 916)) as left, image.crop((902, 200, 1682, 916)) as right:
            assert ImageChops.difference(left, right).getbbox() == (0, 0, 780, 716)
    first = render("film-frame", 1, original, SEED)
    assert first == render("film-frame", 1, original, SEED)
    assert first != render("film-frame", 1, original, UUID(int=3))
