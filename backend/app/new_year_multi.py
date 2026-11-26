"""New Year multi-photo overlays, measured photo windows, and print previews."""

from contextlib import ExitStack
from dataclasses import dataclass, replace
from functools import lru_cache
from math import dist
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageOps

from app.filmstrip import print_jpeg
from app.multi_photo import NewYearPlan, NewYearTemplate

ARTWORK = Path(__file__).parent / "assets"
ARTWORK_SIZE = (1024, 1536)
PRINT_SIZE = (1200, 1800)
ARTWORK_SIZES = {
    NewYearTemplate.GLITTERING_WELCOME: (1536, 1024),
    NewYearTemplate.CHAMPAGNE_CHEERS: (1696, 2528),
    NewYearTemplate.NEW_YEARS_EVE: (1696, 2528),
    NewYearTemplate.BURGUNDY_CELEBRATION: (1536, 1024),
    NewYearTemplate.RETRO_CONFETTI: (2528, 1696),
    NewYearTemplate.AURORA_CELEBRATION: (1536, 1024),
}
ALPHA_CUTOUT_TEMPLATES = frozenset((
    NewYearTemplate.RADIANT_WELCOME, NewYearTemplate.HELLO_2027, NewYearTemplate.GLITTERING_WELCOME,
    NewYearTemplate.WELCOME_CELEBRATION, NewYearTemplate.CHAMPAGNE_CHEERS, NewYearTemplate.NEW_YEARS_EVE,
    NewYearTemplate.BURGUNDY_CELEBRATION, NewYearTemplate.RETRO_CONFETTI, NewYearTemplate.AURORA_CELEBRATION,
))
TOP_ALIGNED_TEMPLATES = frozenset((
    NewYearTemplate.BURGUNDY_CELEBRATION, NewYearTemplate.RETRO_CONFETTI, NewYearTemplate.AURORA_CELEBRATION,
))
Point = tuple[int, int]
Polygon = tuple[Point, ...]


@dataclass(frozen=True)
class PhotoWindow:
    photo: int
    corners: Polygon  # top left, top right, bottom right, bottom left
    visible: Polygon = ()
    oval: bool = False
    behind_oval: bool = False
    preserve: tuple[Polygon, ...] = ()


# Coordinates use each supplied artwork's original canvas.
# Visible outlines retain overlapping Polaroids, metal corners, tape, and flowers.
WINDOWS = {
    NewYearTemplate.MIDNIGHT_MEMORIES: tuple(
        PhotoWindow(index, ((56, top), (554, top), (554, bottom), (56, bottom)))
        for index, (top, bottom) in enumerate(((76, 401), (433, 745), (778, 1071), (1107, 1422)))
    ),
    NewYearTemplate.FRESH_CHAPTER: (
        PhotoWindow(0, ((64, 269), (369, 277), (348, 706), (39, 698)), behind_oval=True,
                    preserve=(((46, 257), (109, 259), (47, 324)),
                              ((282, 713), (356, 649), (353, 719)))),
        PhotoWindow(1, ((650, 274), (968, 252), (992, 701), (672, 715)), behind_oval=True,
                    preserve=(((916, 246), (978, 242), (985, 307)),
                              ((941, 714), (1000, 649), (1005, 718)))),
        PhotoWindow(2, ((294, 628), (715, 628), (715, 1071), (294, 1071)), oval=True,
                    preserve=(((295, 918), (308, 913), (321, 924), (327, 938), (320, 950),
                               (336, 964), (337, 979), (351, 991), (348, 1006), (331, 1003),
                               (321, 985), (302, 975)),)),
        PhotoWindow(3, ((49, 1021), (277, 991), (310, 1235), (79, 1263)),
                    visible=((49, 1021), (110, 1013), (110, 1017), (211, 1004), (210, 1000),
                             (277, 991), (310, 1235), (79, 1263))),
        PhotoWindow(4, ((740, 978), (974, 1008), (941, 1264), (708, 1235)),
                    visible=((740, 978), (810, 987), (810, 997), (920, 1014), (922, 1001),
                             (974, 1008), (941, 1264), (708, 1235))),
    ),
    NewYearTemplate.PARTY_AFTER_DARK: (
        PhotoWindow(0, ((58, 250), (460, 180), (522, 544), (118, 608)),
                    visible=((58, 250), (460, 180), (502, 462), (378, 443), (355, 569), (118, 608))),
        PhotoWindow(1, ((395, 475), (794, 534), (727, 896), (322, 833)),
                    visible=((395, 475), (794, 534), (727, 896), (511, 863), (507, 829), (385, 843), (322, 833))),
        PhotoWindow(2, ((82, 908), (489, 859), (532, 1221), (130, 1268)),
                    preserve=(((185, 1217), (197, 1221), (212, 1230), (219, 1246), (216, 1260),
                               (204, 1273), (178, 1276), (159, 1264), (151, 1250), (155, 1233), (170, 1222)),)),
        # The strip reprises the three large portraits and adds the fourth capture.
        PhotoWindow(0, ((864, 583), (991, 607), (969, 708), (841, 686))),
        PhotoWindow(1, ((839, 700), (966, 723), (948, 826), (818, 802))),
        PhotoWindow(2, ((815, 817), (945, 840), (925, 943), (795, 919))),
        PhotoWindow(3, ((792, 934), (921, 957), (901, 1060), (772, 1036))),
    ),
    NewYearTemplate.SPARKLE_SEASON: tuple(
        PhotoWindow(index, ((528, top), (998, top), (998, bottom), (528, bottom)))
        for index, (top, bottom) in enumerate(((43, 378), (411, 744), (779, 1096), (1131, 1468)))
    ),
    NewYearTemplate.RADIANT_WELCOME: (
        PhotoWindow(0, ((52, 94), (497, 33), (561, 477), (113, 531))),
        PhotoWindow(1, ((597, 359), (982, 414), (898, 942), (530, 887))),
        PhotoWindow(2, ((54, 695), (488, 611), (536, 888), (102, 965))),
        PhotoWindow(3, ((216, 996), (863, 932), (901, 1353), (254, 1415))),
    ),
    NewYearTemplate.HELLO_2027: (
        PhotoWindow(0, ((32, 107), (511, 47), (557, 496), (83, 550))),
        PhotoWindow(1, ((626, 375), (1001, 441), (901, 862), (549, 792))),
        PhotoWindow(2, ((36, 619), (460, 562), (493, 836), (73, 890))),
        PhotoWindow(3, ((388, 906), (968, 881), (939, 1308), (337, 1267))),
    ),
    NewYearTemplate.GLITTERING_WELCOME: (
        PhotoWindow(0, ((85, 170), (531, 78), (581, 395), (142, 483))),
        PhotoWindow(1, ((1108, 60), (1498, 130), (1431, 454), (1037, 381))),
        PhotoWindow(2, ((235, 517), (661, 585), (611, 882), (185, 826))),
        PhotoWindow(3, ((703, 485), (1367, 433), (1392, 816), (733, 863))),
    ),
    NewYearTemplate.WELCOME_CELEBRATION: (
        PhotoWindow(0, ((49, 97), (473, 48), (521, 580), (112, 630))),
        PhotoWindow(1, ((579, 438), (978, 489), (904, 888), (512, 837))),
        PhotoWindow(2, ((81, 702), (447, 640), (503, 965), (129, 1015))),
        PhotoWindow(3, ((301, 1035), (902, 947), (952, 1345), (361, 1425))),
    ),
    NewYearTemplate.CHAMPAGNE_CHEERS: (
        PhotoWindow(0, ((172, 475), (765, 395), (820, 821), (229, 902))),
        PhotoWindow(1, ((983, 450), (1547, 512), (1458, 1305), (896, 1242))),
        PhotoWindow(2, ((169, 1066), (725, 992), (828, 1801), (275, 1874))),
        PhotoWindow(3, ((980, 1406), (1547, 1472), (1497, 1878), (931, 1809))),
    ),
    NewYearTemplate.NEW_YEARS_EVE: (
        PhotoWindow(0, ((173, 685), (742, 598), (850, 1285), (281, 1374))),
        PhotoWindow(1, ((990, 596), (1514, 694), (1396, 1311), (871, 1212))),
        PhotoWindow(2, ((148, 1533), (624, 1404), (782, 1940), (307, 2073))),
        PhotoWindow(3, ((955, 1265), (1554, 1355), (1431, 2150), (831, 2060))),
    ),
    NewYearTemplate.BURGUNDY_CELEBRATION: (
        PhotoWindow(0, ((91, 98), (636, 98), (636, 477), (91, 477))),
        PhotoWindow(1, ((601, 241), (927, 241), (927, 767), (601, 767))),
        PhotoWindow(2, ((176, 546), (542, 546), (542, 834), (176, 834))),
        PhotoWindow(3, ((916, 546), (1445, 546), (1445, 922), (916, 922)),
                    # The tall central frame sits in front of this photograph.
                    visible=((938, 532), (1458, 532), (1458, 936), (902, 936), (902, 780), (938, 780))),
    ),
    NewYearTemplate.RETRO_CONFETTI: (
        PhotoWindow(0, ((143, 150), (1148, 150), (1148, 806), (143, 806))),
        PhotoWindow(1, ((1325, 150), (2386, 150), (2386, 806), (1325, 806))),
        PhotoWindow(2, ((143, 1018), (906, 1018), (906, 1547), (143, 1547))),
        PhotoWindow(3, ((1062, 927), (1514, 927), (1514, 1547), (1062, 1547))),
    ),
    NewYearTemplate.AURORA_CELEBRATION: (
        PhotoWindow(0, ((183, 174), (651, 88), (711, 375), (239, 453))),
        PhotoWindow(1, ((951, 25), (1350, 100), (1200, 539), (869, 448))),
        PhotoWindow(2, ((157, 471), (488, 554), (427, 804), (94, 719))),
        PhotoWindow(3, ((806, 621), (1410, 528), (1320, 877), (664, 930))),
    ),
}


def artwork_path(template: NewYearTemplate) -> Path:
    return ARTWORK / f"new-year-multi-{template}.png"


def artwork_size(template: NewYearTemplate) -> tuple[int, int]:
    return ARTWORK_SIZES.get(template, ARTWORK_SIZE)


def print_size(template: NewYearTemplate) -> tuple[int, int]:
    width, height = artwork_size(template)
    return PRINT_SIZE[::-1] if width > height else PRINT_SIZE


def preview_size(template: NewYearTemplate) -> tuple[int, int]:
    return tuple(value * 2 // 5 for value in print_size(template))


def placement_window(template: NewYearTemplate, window: PhotoWindow) -> PhotoWindow:
    """Bleed photographs beneath the frame to cover irregular alpha-cutout edges."""
    if template not in ALPHA_CUTOUT_TEMPLATES:
        return window
    # New Year's Eve has two differently tilted frames around the third photo;
    # its small exposed rear-frame corners need a wider underlay.
    scale = (1.24 if template == NewYearTemplate.NEW_YEARS_EVE and window.photo == 2
             else 1.12 if template == NewYearTemplate.AURORA_CELEBRATION else 1.08)
    center_x, center_y = (sum(point[axis] for point in window.corners) / 4 for axis in (0, 1))
    corners = tuple((round(center_x + (x - center_x) * scale), round(center_y + (y - center_y) * scale))
                    for x, y in window.corners)
    return replace(window, corners=corners)


def window_mask(window: PhotoWindow, size: tuple[int, int] = ARTWORK_SIZE) -> Image.Image:
    """Antialias the measured opening without erasing foreground decoration."""
    scale = 3
    with Image.new("L", tuple(value * scale for value in size)) as mask:
        draw = ImageDraw.Draw(mask)
        points = lambda polygon: [(x * scale, y * scale) for x, y in polygon]
        if window.oval:
            left, top = window.corners[0]
            right, bottom = window.corners[2]
            draw.ellipse((left * scale, top * scale, right * scale, bottom * scale), fill=255)
        else:
            draw.polygon(points(window.visible or window.corners), fill=255)
        if window.behind_oval:
            draw.ellipse(tuple(value * scale for value in (279, 609, 732, 1089)), fill=0)
        for polygon in window.preserve:
            draw.polygon(points(polygon), fill=0)
        return mask.resize(size, Image.Resampling.LANCZOS)


def _perspective(corners: Polygon, width: int, height: int) -> tuple[float, ...]:
    """Map the artwork quadrilateral back into an upright source photograph."""
    rows = []
    for (x, y), (u, v) in zip(corners, ((0, 0), (width, 0), (width, height), (0, height)), strict=True):
        rows.extend(([x, y, 1, 0, 0, 0, -u * x, -u * y, u],
                     [0, 0, 0, x, y, 1, -v * x, -v * y, v]))
    for column in range(8):
        pivot = max(range(column, 8), key=lambda row: abs(rows[row][column]))
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [value / divisor for value in rows[column]]
        for row in range(8):
            if row != column:
                factor = rows[row][column]
                rows[row] = [value - factor * term for value, term in zip(rows[row], rows[column], strict=True)]
    return tuple(row[-1] for row in rows)


def _compose(sources: Sequence[Path | Image.Image], plan: NewYearPlan, *, preview: bool = False) -> bytes:
    if len(sources) != plan.count:
        raise ValueError("The number of originals must match the capture plan")
    canvas_size = artwork_size(plan.template)
    with Image.open(artwork_path(plan.template), formats=("PNG",)) as overlay, \
            Image.new("RGB", canvas_size, "white") as canvas:
        for window in WINDOWS[plan.template]:
            window = placement_window(plan.template, window)
            tl, tr, br, bl = window.corners
            size = round((dist(tl, tr) + dist(bl, br)) / 2), round((dist(tl, bl) + dist(tr, br)) / 2)
            source = sources[window.photo]
            with (Image.open(source, formats=("JPEG",)) if isinstance(source, Path) else source.copy()) as photo:
                ImageOps.exif_transpose(photo, in_place=True)
                with photo.convert("RGB") as rgb, \
                        ImageOps.fit(rgb, size, Image.Resampling.LANCZOS,
                                     centering=(.5, 0 if plan.template in TOP_ALIGNED_TEMPLATES else .35)) as crop, \
                        crop.transform(canvas_size, Image.Transform.PERSPECTIVE,
                                       _perspective(window.corners, *size), Image.Resampling.BICUBIC) as fitted, \
                        window_mask(window, canvas_size) as mask:
                    canvas.paste(fitted, (0, 0), mask)
        canvas.paste(overlay, (0, 0), overlay.getchannel("A"))
        with canvas.resize(preview_size(plan.template) if preview else print_size(plan.template), Image.Resampling.LANCZOS) as output:
            return print_jpeg(output)


def render_new_year(originals: Sequence[Path], plan: NewYearPlan) -> bytes:
    return _compose(originals, plan)


@lru_cache(maxsize=len(NewYearTemplate))
def new_year_preview(template: NewYearTemplate) -> bytes:
    # Reuse the existing offline sample photographs; previews use the production compositor.
    with ExitStack() as images:
        sample = images.enter_context(Image.open(ARTWORK / "motion-study-sample.jpg"))
        width, height = sample.width // 3, sample.height // 2
        sources = []
        for index in range(template.count):
            left, top = (index % 3) * width, (index // 3) * height
            sources.append(images.enter_context(sample.crop((left, top, left + width, top + height))))
        return _compose(sources, NewYearPlan(template=template, count=template.count), preview=True)
