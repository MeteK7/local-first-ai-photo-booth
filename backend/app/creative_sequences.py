"""Editorial and motion compositions for the Multi-Photo Studio Creative Collection."""

from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont

from app.filmstrip import FrameBox, GRID_HEIGHT, GRID_WIDTH, cells, paste_frame, print_jpeg
from app.motion_study import motion_panels, render_motion_study
from app.multi_photo import (
    MINI_SCENE_BEATS, BetweenFramesPlan, CreativePlan, MiniScenePlan, MotionStudyPlan, TimeSculpturePlan, capture_directions,
)


def creative_boxes(plan: CreativePlan) -> list[FrameBox]:
    if isinstance(plan, BetweenFramesPlan):
        return [(x, 237, width, 776) for x, width in cells(GRID_WIDTH, plan.count, 86)]
    if isinstance(plan, MiniScenePlan):
        return [(86, 232, 484, 494), (606, 232, 1108, 494), (86, 818, 720, 310), (842, 818, 872, 310)]
    if isinstance(plan, TimeSculpturePlan):
        return [(index * 600, 0, 600, 1200) for index in range(3)]
    if isinstance(plan, MotionStudyPlan) and plan.layout is not None:
        return [panel.box() for panel in motion_panels(plan.layout, plan.count)]

    # Walking left to right, successive frames alternate in height along a rising path.
    lead = [
        (84 + 690 * index // (plan.count - 2), (650 if index % 2 == 0 else 355) - 24 * index, 265, 210)
        for index in range(plan.count - 1)
    ]
    return [*lead, (1080, 243, 640, 625)]


def render_creative_sequence(originals: Sequence[Path], plan: CreativePlan) -> bytes:
    if isinstance(plan, TimeSculpturePlan) or len(originals) != plan.count:
        raise ValueError("The number of originals must match the capture plan")
    if isinstance(plan, MotionStudyPlan) and plan.layout is not None:
        return render_motion_study(originals, plan.layout)

    boxes = creative_boxes(plan)
    between = isinstance(plan, BetweenFramesPlan)
    storyboard = isinstance(plan, MiniScenePlan)
    paper = "#f4f3f0" if between else "#172233"
    ink = "#26354a" if between else "#eef3f9"
    accent = "#778699" if between else "#a4bddd"
    padding = "#e8e8e5" if between else "#25354a"
    with Image.new("RGB", (GRID_WIDTH, GRID_HEIGHT), paper) as canvas:
        draw = ImageDraw.Draw(canvas)
        draw.text((86, 89), capture_directions(plan).title, font=ImageFont.load_default(70), fill=ink)
        draw.line((86, 195, 1714, 195), fill=accent, width=2)
        if not between and not storyboard:
            centers = [(x + w // 2, y + h // 2) for x, y, w, h in boxes]
            draw.line(centers, fill=accent, width=4, joint="curve")
            draw.line((86, 973, 1714, 973), fill=accent, width=2)

        index_font = ImageFont.load_default(27)
        for number, (path, box) in enumerate(zip(originals, boxes, strict=True), 1):
            x, y, width, height = box
            draw.rectangle((x - 2, y - 2, x + width + 1, y + height + 1), outline=accent, width=2)
            paste_frame(canvas, path, box, padding=padding)
            caption = f"{number:02d} · {MINI_SCENE_BEATS[number - 1]}" if storyboard else f"{number:02d}"
            draw.text((x, y + height + 16), caption, font=index_font, fill=ink)

        return print_jpeg(canvas)
