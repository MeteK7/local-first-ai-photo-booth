from io import BytesIO

import pytest
from PIL import Image

from app.filmstrip import frame_boxes, render_filmstrip
from app.multi_photo import SignatureStripPlan, StripLayout


@pytest.fixture
def originals(tmp_path):
    fields = [(215, 36, 30), (32, 161, 80), (24, 76, 194), (227, 176, 36), (139, 38, 156), (25, 168, 174)]
    paths = []
    for index, color in enumerate(fields):
        path = tmp_path / f"source-{index}.jpg"
        size = (120, 80) if index % 2 == 0 else (80, 120)
        with Image.new("RGB", size, color) as image:
            image.save(path, "JPEG")
        paths.append(path)
    return paths, fields


@pytest.mark.parametrize("count", range(2, 7))
@pytest.mark.parametrize(("layout", "size"), [
    (StripLayout.VERTICAL, (600, 1800)),
    (StripLayout.HORIZONTAL, (1800, 600)),
    (StripLayout.GRID, (1800, 1200)),
])
def test_signature_strip_has_print_dimensions_and_preserves_frame_order(originals, count, layout, size):
    paths, fields = originals
    plan = SignatureStripPlan(count=count, layout=layout)
    frames = frame_boxes(plan)
    assert len(frames) == count
    with Image.open(BytesIO(render_filmstrip(paths[:count], plan))) as strip:
        assert strip.size == size
        assert strip.info["dpi"] == (300, 300)
        assert strip.getpixel((3, 3)) == (255, 255, 255)
        for (x, y, width, height), color in zip(frames, fields[:count], strict=True):
            assert x > 0 and y > 0 and x + width < strip.width and y + height < strip.height
            center = strip.getpixel((x + width // 2, y + height // 2))
            assert max(abs(a - b) for a, b in zip(center, color, strict=True)) < 4


def test_portrait_exif_rotation_and_safe_crop_keep_both_edges(tmp_path):
    source = tmp_path / "phone.jpg"
    with Image.new("RGB", (180, 100), (230, 65, 40)) as image:
        image.paste((25, 75, 215), (90, 0, 180, 100))
        exif = image.getexif()
        exif[274] = 6
        image.save(source, "JPEG", exif=exif)
    original = source.read_bytes()
    plan = SignatureStripPlan(count=2, layout=StripLayout.HORIZONTAL)
    x, y, width, height = frame_boxes(plan)[0]
    with Image.open(BytesIO(render_filmstrip([source, source], plan))) as strip:
        assert strip.getpixel((x + width // 2, y + 25))[0] > 210
        assert strip.getpixel((x + width // 2, y + height - 25))[2] > 195
        gutter = strip.getpixel((x + 20, y + height // 2))
        assert min(gutter) > 210
    assert source.read_bytes() == original
