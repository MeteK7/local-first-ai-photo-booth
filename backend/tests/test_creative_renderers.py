from hashlib import sha256
from io import BytesIO
from uuid import UUID

import pytest
from PIL import Image, ImageChops, ImageDraw

from app.creative_renderers import ARTWORK, CATALOG, NEW_YEAR_PHOTO_BOXES, detail_regions, render, station_portrait_layers

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
    variants = [render(name, recipe.version, original, SEED) for name, recipe in CATALOG.items()]
    assert len(set(variants)) == len(CATALOG)
    for name, jpeg in zip(CATALOG, variants, strict=True):
        with Image.open(BytesIO(jpeg)) as image:
            image.load()
            assert image.mode == "RGB"
            assert not image.getexif()
            if name != "classic-filter":
                vertical = ((name == "portrait-atlas" and portrait)
                            or (CATALOG[name].category == "frame" and name.endswith("-portrait")))
                if name == "hazar-station-portrait":
                    expected = (1056, 1429)
                elif CATALOG[name].category == "new-year-frame":
                    with Image.open(ARTWORK / f"{name}.png") as artwork:
                        expected = artwork.size
                else:
                    expected = (1200, 1800) if vertical else (1800, 1200)
                assert image.size == expected and image.info["dpi"] == (300, 300)


@pytest.mark.parametrize("name", [name for name, recipe in CATALOG.items() if recipe.category == "frame"])
def test_hazar_frame_shows_the_original_color_through_its_window(name):
    with Image.open(ARTWORK / f"{name}.png") as artwork, artwork.getchannel("A") as alpha:
        w, h = artwork.size
        with alpha.crop((w * 2 // 5, h * 2 // 5, w * 3 // 5, h * 3 // 5)) as center:
            assert center.getextrema()[1] <= 1
    original = sample((720, 480), textured=False)
    with Image.open(BytesIO(render(name, CATALOG[name].version, original, SEED))) as photo:
        pixel = photo.getpixel((photo.width // 2, photo.height // 2))
        assert all(abs(actual - expected) < 4 for actual, expected in zip(pixel, (45, 65, 77), strict=True))
        with photo.crop((0, photo.height * 9 // 10, photo.width, photo.height)) as footer:
            assert any(high - low > 32 for low, high in footer.getextrema())


@pytest.mark.parametrize("name", [name for name, recipe in CATALOG.items() if recipe.category == "new-year-frame"])
def test_new_year_frame_fills_the_opening_and_preserves_the_artwork(name):
    original = sample((720, 480), textured=False)
    with (Image.open(ARTWORK / f"{name}.png") as artwork,
          Image.open(BytesIO(render(name, CATALOG[name].version, original, SEED))) as photo):
        w, h = artwork.size
        assert photo.size == artwork.size
        left, top, right, bottom = NEW_YEAR_PHOTO_BOXES.get(name, (0, 0, w, h))
        width, height = right - left, bottom - top
        with photo.crop((left + width * 2 // 5, top + height * 2 // 5,
                         left + width * 3 // 5, top + height * 3 // 5)) as window:
            expected = (45, 65, 77)
            assert all(abs(value - channel) <= 4 for pair, channel in zip(window.getextrema(), expected, strict=True)
                       for value in pair)
        for x, y in ((w // 2, h // 16), (w // 2, h * 15 // 16), (w * 4 // 5, h * 15 // 16)):
            source = artwork.getpixel((x, y))
            if artwork.mode == "RGB" or source[3] >= 250:
                assert all(abs(actual - reference) <= 16
                           for actual, reference in zip(photo.getpixel((x, y)), source[:3], strict=True))


@pytest.mark.parametrize("name", NEW_YEAR_PHOTO_BOXES)
def test_offset_new_year_window_keeps_the_subject_centered_and_preserves_decorations(name):
    with Image.new("RGB", (800, 800), "#2d414d") as source, BytesIO() as jpeg:
        ImageDraw.Draw(source).ellipse((300, 300, 500, 500), fill="#ef7144")
        source.save(jpeg, "JPEG")
        with (Image.open(ARTWORK / f"{name}.png") as artwork,
              Image.open(BytesIO(render(name, CATALOG[name].version, jpeg.getvalue(), SEED))) as photo):
            left, top, right, bottom = NEW_YEAR_PHOTO_BOXES[name]
            center = ((left + right) // 2, (top + bottom) // 2)
            assert artwork.getpixel(center)[3] <= 1
            assert all(abs(actual - expected) <= 4
                       for actual, expected in zip(photo.getpixel(center), (239, 113, 68), strict=True))
            for position in ((100, 100), (300, 400), (1000, 950), (1450, 900)):
                assert artwork.getpixel(position)[3] >= 250


@pytest.mark.parametrize("background", [(45, 65, 77), (180, 140, 100)])
def test_cozy_winter_retains_its_translucent_inner_glow(background):
    name = "new-year-cozy-winter-landscape"
    # Native RGBA values at the rounded corners, inner sides and lower edge.
    # The glow must blend with the photograph rather than become a hard cutout.
    glow = {
        (810, 170): (217, 214, 211, 166),
        (790, 210): (239, 238, 236, 120),
        (770, 400): (232, 230, 228, 81),
        (1400, 500): (227, 224, 223, 31),
        (1086, 850): (241, 239, 237, 43),
    }
    with Image.new("RGB", (800, 800), background) as original, BytesIO() as jpeg:
        original.save(jpeg, "JPEG", quality=100, subsampling=0)
        with (Image.open(BytesIO(jpeg.getvalue())) as decoded,
              Image.open(ARTWORK / f"{name}.png") as artwork,
              Image.open(BytesIO(render(name, CATALOG[name].version, jpeg.getvalue(), SEED))) as photo):
            source = decoded.getpixel((0, 0))
            for position, rgba in glow.items():
                assert artwork.getpixel(position) == rgba
                expected = tuple(round(channel * rgba[3] / 255 + base * (1 - rgba[3] / 255))
                                 for channel, base in zip(rgba[:3], source, strict=True))
                assert all(abs(actual - reference) <= 4
                           for actual, reference in zip(photo.getpixel(position), expected, strict=True))


def test_vertical_station_cleans_only_the_faint_exterior_fringe():
    with Image.open(ARTWORK / "hazar-station-portrait.png") as source:
        artwork, opening = station_portrait_layers(source)
        with (artwork, opening, source.convert("RGB") as before, artwork.convert("RGB") as after,
              source.getchannel("A") as original_alpha, artwork.getchannel("A") as cleaned_alpha):
            assert artwork.size == source.size
            assert ImageChops.difference(before, after).getbbox() is None
            with ImageChops.difference(original_alpha, cleaned_alpha) as removed:
                assert 0 < removed.getextrema()[1] < 64
            assert cleaned_alpha.getbbox()[1] > original_alpha.getbbox()[1]
            assert cleaned_alpha.getbbox()[3] < original_alpha.getbbox()[3]
            assert opening.getpixel((145, 700)) == opening.getpixel((940, 700)) == 255
            assert opening.getpixel((100, 700)) == opening.getpixel((990, 700)) == 0
            assert cleaned_alpha.getpixel((source.width // 2, source.height // 2)) == 0


def test_vertical_station_canvas_stops_at_the_artwork_bounds():
    original = sample((720, 480), textured=False)
    name = "hazar-station-portrait"
    with Image.open(BytesIO(render(name, CATALOG[name].version, original, SEED))) as photo:
        assert photo.size == (1056, 1429)
        for box in ((8, 450, 16, 1000), (1040, 450, 1048, 1000)):
            with photo.crop(box) as outside:
                assert outside.getextrema() == ((255, 255),) * 3
        for box in ((0, 0, photo.width, 12), (0, photo.height - 12, photo.width, photo.height)):
            with photo.crop(box) as edge:
                assert edge.getextrema()[0][0] < 240


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
