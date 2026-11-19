from io import BytesIO

import pytest
from PIL import Image
from pydantic import ValidationError

from app.creative_sequences import render_creative_sequence
from app.filmstrip import GRID_HEIGHT, GRID_WIDTH
from app.motion_study import MOTION_DESIGNS, motion_panels, motion_preview
from app.multi_photo import MotionStudyLayout, MotionStudyPlan


@pytest.mark.parametrize(("layout", "count"), [
    (MotionStudyLayout.CONTACT_STACK, 4),
    (MotionStudyLayout.MATCH_CUT, 4),
    (MotionStudyLayout.ASCENDING_CUT, 4),
    (MotionStudyLayout.ASCENDING_CUT, 5),
    (MotionStudyLayout.ASCENDING_CUT, 6),
])
def test_motion_layout_uses_ordered_originals_in_a_landscape_print(tmp_path, layout, count):
    colors = [(211, 43, 22), (31, 168, 75), (40, 82, 194), (218, 178, 45), (134, 50, 162), (30, 180, 185)]
    originals = []
    for index, color in enumerate(colors[:count]):
        image_path = tmp_path / f"frame-{index}.jpg"
        with Image.new("RGB", (240, 160) if index % 2 else (160, 240), color) as image:
            image.save(image_path, "JPEG")
        originals.append(image_path)

    source_bytes = [path.read_bytes() for path in originals]
    plan = MotionStudyPlan(experience="motion-study", layout=layout, count=count)
    with Image.open(BytesIO(render_creative_sequence(originals, plan))) as print_image:
        assert print_image.size == (GRID_WIDTH, GRID_HEIGHT)
        assert print_image.info["dpi"] == (300, 300)
        for panel, color in zip(motion_panels(layout, count), colors[:count], strict=True):
            x, y, width, height = panel.box()
            center = print_image.getpixel((x + width // 2, y + height // 2))
            assert max(abs(value - expected) for value, expected in zip(center, color, strict=True)) < 4
    assert [path.read_bytes() for path in originals] == source_bytes
    with Image.open(BytesIO(motion_preview(layout, count))) as preview:
        assert preview.size == (720, 480)
        paper = bytes.fromhex(MOTION_DESIGNS[layout].paper.removeprefix("#"))
        assert max(abs(a - b) for a, b in zip(preview.getpixel((2, 2)), paper, strict=True)) < 4


def test_match_cut_gutters_are_equal_along_all_shared_edges():
    panels = motion_panels(MotionStudyLayout.MATCH_CUT, 4)

    def edge(panel, top, bottom, y):
        slope = (bottom - top) / panel.height
        return panel.x + panel.width * (top + slope * (y - panel.y)) / 100

    assert panels[2].width > max(panel.width for index, panel in enumerate(panels) if index != 2) * 1.45
    for left, right in zip(panels, panels[1:]):
        upper = max(left.y, right.y)
        lower = min(left.y + left.height, right.y + right.height)
        assert upper < lower
        for y in (upper, (upper + lower) / 2, lower):
            gap = edge(right, right.cut[0][0], right.cut[3][0], y) - edge(left, left.cut[1][0], left.cut[2][0], y)
            assert gap == pytest.approx(.48)


@pytest.mark.parametrize("layout", [MotionStudyLayout.CONTACT_STACK, MotionStudyLayout.MATCH_CUT])
def test_four_frame_layout_rejects_other_counts_without_affecting_saved_plans(layout):
    with pytest.raises(ValidationError):
        MotionStudyPlan(experience="motion-study", layout=layout, count=5)
    old = {"experience": "motion-study", "version": 1, "count": 5}
    assert MotionStudyPlan.model_validate(old).model_dump(mode="json") == old
