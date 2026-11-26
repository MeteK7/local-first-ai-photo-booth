from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageChops
from pydantic import ValidationError

from app.multi_photo import NewYearPlan, NewYearTemplate, capture_directions, print_layout, StripLayout
from app.new_year_multi import (WINDOWS, artwork_path, artwork_size, placement_window, print_size,
                               preview_size, render_new_year, window_mask)
from app.sessions import PLAN_ADAPTER, router


@pytest.mark.parametrize("template", NewYearTemplate)
def test_new_year_print_fills_every_window_in_capture_order_and_preserves_artwork(tmp_path, template):
    colors = [(215, 36, 30), (32, 161, 80), (24, 76, 194), (227, 176, 36), (139, 38, 156)]
    plan = NewYearPlan(template=template, count=template.count)
    paths = []
    for index, color in enumerate(colors[:plan.count]):
        path = tmp_path / f"{index}.jpg"
        with Image.new("RGB", (180, 120), color) as source:
            source.save(path)
        paths.append(path)
    originals = [path.read_bytes() for path in paths]
    source_size, output_size = artwork_size(template), print_size(template)
    scale_x, scale_y = (target / source for target, source in zip(output_size, source_size, strict=True))
    with Image.open(artwork_path(template)) as overlay, Image.open(BytesIO(render_new_year(paths, plan))) as printout:
        assert overlay.mode == "RGBA" and overlay.size == source_size
        assert printout.size == output_size and printout.info["dpi"] == (300, 300)
        for window in WINDOWS[template]:
            x = round(sum(point[0] for point in window.corners) / 4)
            y = round(sum(point[1] for point in window.corners) / 4)
            assert overlay.getpixel((x, y))[3] <= 1
            actual = printout.getpixel((round(x * scale_x), round(y * scale_y)))
            assert max(abs(a - b) for a, b in zip(actual, colors[window.photo], strict=True)) < 5
        # The decorative banner and outer corners remain opaque and retain their colors.
        with overlay.convert("RGB") as artwork, artwork.resize(output_size, Image.Resampling.LANCZOS) as reference:
            for x, y in ((10, 10), (source_size[0] - 10, source_size[1] - 10), (source_size[0] // 2, source_size[1] - 10)):
                assert overlay.getpixel((x, y))[3] == 255
                point = round(x * scale_x), round(y * scale_y)
                assert max(abs(a - b) for a, b in zip(printout.getpixel(point), reference.getpixel(point), strict=True)) < 15
    assert [path.read_bytes() for path in paths] == originals
    assert print_layout(plan) == StripLayout.GRID  # Existing Photo profile detects orientation from the JPEG.
    assert capture_directions(plan).title_key == "studio.experience.new-year.name"


@pytest.mark.parametrize("template", NewYearTemplate)
def test_new_year_plan_round_trips_and_rejects_wrong_counts(template):
    selected = NewYearPlan(template=template, count=template.count)
    assert PLAN_ADAPTER.validate_json(selected.model_dump_json()) == selected
    with pytest.raises(ValidationError):
        NewYearPlan(template=template, count=4 if template.count == 5 else 5)
    with pytest.raises(ValidationError):
        PLAN_ADAPTER.validate_python({**selected.model_dump(), "template": "untrusted-path"})


def test_new_year_catalog_previews_and_invalid_template():
    app = FastAPI()
    app.state.settings = type("Settings", (), {"time_sculpture_enabled": False})()
    app.include_router(router)
    with TestClient(app) as client:
        choices = client.get("/api/sessions/multi-photo-studio").json()["new_year"]
        assert [choice["id"] for choice in choices] == list(NewYearTemplate)
        for choice in choices:
            assert choice["default_plan"]["count"] == NewYearTemplate(choice["id"]).count
            response = client.get(choice["preview"])
            assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
            with Image.open(BytesIO(response.content)) as preview:
                assert preview.size == preview_size(NewYearTemplate(choice["id"]))
                assert preview.size == (choice["preview_width"], choice["preview_height"])
            width, height = print_size(NewYearTemplate(choice["id"]))
            assert choice["size"] == ("6 × 4 in" if width > height else "4 × 6 in")
        assert client.get("/api/sessions/multi-photo-studio/new-year/unknown/preview").status_code == 422


def test_fresh_chapter_and_party_keep_foreground_overlaps():
    with Image.open(artwork_path(NewYearTemplate.FRESH_CHAPTER)) as overlay:
        for point in ((67, 286), (340, 701), (675, 697), (873, 1002), (310, 940)):
            assert overlay.getpixel(point)[3] == 255
    with Image.open(artwork_path(NewYearTemplate.PARTY_AFTER_DARK)) as overlay:
        for point in ((410, 464), (505, 841), (186, 1249)):
            assert overlay.getpixel(point)[3] == 255


@pytest.mark.parametrize(("template", "decorations"), [
    (NewYearTemplate.RADIANT_WELCOME, ((500, 445), (944, 390), (88, 936), (848, 1330))),
    (NewYearTemplate.HELLO_2027, ((78, 91), (937, 410), (520, 788), (900, 1294))),
    (NewYearTemplate.GLITTERING_WELCOME, ((165, 145), (1435, 120), (604, 868), (1347, 780),
                                        (233, 830), (272, 836))),
    (NewYearTemplate.WELCOME_CELEBRATION, ((78, 115), (946, 706), (878, 1344))),
    (NewYearTemplate.CHAMPAGNE_CHEERS, ((418, 1870), (810, 2175), (1508, 2396))),
    (NewYearTemplate.NEW_YEARS_EVE, ((1455, 700), (1424, 1034), (425, 2320))),
    (NewYearTemplate.BURGUNDY_CELEBRATION, ((516, 437), (735, 270), (633, 302), (236, 601),
                                         (603, 675), (1050, 900))),
    (NewYearTemplate.RETRO_CONFETTI, ((120, 200), (800, 120), (1305, 250), (1500, 910))),
    (NewYearTemplate.AURORA_CELEBRATION, ((550, 450), (784, 272), (900, 540), (147, 749), (1350, 851))),
])
def test_added_templates_preserve_foreground_decorations(template, decorations):
    with Image.open(artwork_path(template)) as overlay:
        for point in decorations:
            assert overlay.getpixel(point)[3] == 255, point


@pytest.mark.parametrize("template", NewYearTemplate)
def test_every_transparent_pixel_is_covered_by_a_photo(template):
    with Image.open(artwork_path(template)) as overlay:
        coverage = Image.new("L", overlay.size)
        for window in WINDOWS[template]:
            with window_mask(placement_window(template, window), overlay.size) as mask:
                combined = ImageChops.lighter(coverage, mask)
            coverage.close()
            coverage = combined
        with coverage, overlay.getchannel("A").point(lambda alpha: 255 if alpha == 0 else 0) as holes, \
                coverage.point(lambda alpha: 255 if alpha >= 254 else 0) as filled, \
                ImageChops.subtract(holes, filled) as uncovered:
            assert uncovered.getbbox() is None


@pytest.mark.parametrize("template", [NewYearTemplate.BURGUNDY_CELEBRATION, NewYearTemplate.RETRO_CONFETTI,
                                      NewYearTemplate.AURORA_CELEBRATION])
def test_soft_frame_transitions_blend_over_photos_instead_of_white(template):
    with Image.open(artwork_path(template)) as overlay, overlay.getchannel("A") as alpha:
        assert sum(alpha.histogram()[1:240]) > 1000
        coverage = Image.new("L", overlay.size)
        for window in WINDOWS[template]:
            with window_mask(placement_window(template, window), overlay.size) as mask:
                combined = ImageChops.lighter(coverage, mask)
            coverage.close()
            coverage = combined
        with (coverage, alpha.point(lambda value: 255 if value <= 240 else 0) as transitions,
              coverage.point(lambda value: 255 if value >= 254 else 0) as filled,
              ImageChops.subtract(transitions, filled) as uncovered):
            assert uncovered.getbbox() is None
