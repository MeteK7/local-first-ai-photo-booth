"""Build single-shoot overlays while retaining the supplied artwork's RGB pixels.

Usage: .venv/Scripts/python scripts/prepare-new-year-single.py SOURCE_DIRECTORY
Use --cutout-directory to import imagegen PNGs named ARTWORK_ID.png as alpha masks.
The checked-in masks allow rebuilding without calling an image service.
Cozy Winter and Fireworks Celebration require RGBA sources copied unchanged,
including their native translucent glows across the entire canvas.
The Pine Cones glow is recovered from its black matte without thresholding the fade.
"""

import argparse
from pathlib import Path
from shutil import copyfile

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
MASKS = Path(__file__).with_name("new-year-single-masks")
SOURCES = {
    "new-year-bright-blue-landscape": "Bright Blue New Year Photo Frame.png",
    "new-year-vibrant-2027-landscape": "Vibrant 2027 New Year Celebration Frame.png",
    "new-year-cozy-winter-landscape": "Happy New Year 2027 Frame.png",
    "new-year-pine-cones-portrait": "Festive New Year Frame with Pine Cones.png",
    "new-year-fireworks-portrait": "2027 Celebration Beneath Fireworks (1).png",
    "new-year-colorful-2027-portrait": "Enlarged Colorful 2027 Celebration.png",
}
SIZE = (1536, 1024)
PINE_CONES = "new-year-pine-cones-portrait"
PINE_CONES_OPENING = (120, 339, 809, 1134)
COLORFUL_2027 = "new-year-colorful-2027-portrait"


def pine_cones_alpha(source, generated):
    """Recover the sky-blue fade flattened over the source's near-black matte."""
    alpha = Image.new("L", source.size, 255)
    pixels, cutout, opacity = source.load(), generated.load(), alpha.load()
    left, top, right, bottom = PINE_CONES_OPENING
    for y in range(top, bottom):
        for x in range(left, right):
            if cutout[x, y] < 252:
                # The blue foreground reaches 255; its black matte has B=2.
                # Retain every intermediate opacity, including the faintest glow.
                opacity[x, y] = max(0, round((pixels[x, y][2] - 2) * 255 / 253))
    return alpha


def remove_black_matte(overlay, alpha):
    pixels, opacity = overlay.load(), alpha.load()
    left, top, right, bottom = PINE_CONES_OPENING
    for y in range(top, bottom):
        for x in range(left, right):
            value = opacity[x, y]
            if 0 < value < 255:
                rgb = tuple(min(255, max(0, round((channel * 255 - matte * (255 - value)) / value)))
                            for channel, matte in zip(pixels[x, y][:3], (0, 0, 2), strict=True))
                pixels[x, y] = (*rgb, 255)


def black_opening_alpha(source, generated):
    """Keep every light or colored decoration opaque; remove only the dark aperture."""
    with (source.getchannel("R") as red, source.getchannel("G") as green,
          source.getchannel("B") as blue, ImageChops.lighter(red, green) as warm,
          ImageChops.lighter(warm, blue) as peak,
          peak.point(lambda value: max(0, min(255, (value - 24) * 255 // 40))) as protected,
          generated.point(lambda value: 0 if value < 16 else 255 if value > 240 else value) as opening):
        alpha = ImageChops.lighter(opening, protected)
    # The thin black outer canvas border is not part of the middle opening.
    alpha.paste(255, (0, 0, source.width, 2))
    return alpha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_directory", type=Path)
    parser.add_argument("--cutout-directory", type=Path)
    parser.add_argument("--artwork", nargs="+", choices=SOURCES)
    args = parser.parse_args()
    for artwork, filename in SOURCES.items():
        if args.artwork and artwork not in args.artwork:
            continue
        original = args.source_directory / filename
        target = ROOT / "backend" / "app" / "assets" / f"{artwork}.png"
        with Image.open(original) as source, source.convert("RGBA") as overlay:
            size = ((1023, 1538) if artwork == COLORFUL_2027 else
                    (1024, 1536) if artwork.endswith("-portrait") else SIZE)
            if source.size != size:
                raise ValueError(f"Unexpected artwork dimensions: {filename}")
            mask_path = MASKS / f"{artwork}.png"
            if artwork in {"new-year-cozy-winter-landscape", "new-year-fireworks-portrait"}:
                if source.mode != "RGBA":
                    raise ValueError(f"{artwork} must retain the supplied RGBA transparency")
                # This native alpha includes the luminous inner-edge transition,
                # corner gradients, gift ribbons and steam. Never key or threshold it.
                MASKS.mkdir(exist_ok=True)
                with source.getchannel("A") as alpha:
                    alpha.save(mask_path)
                copyfile(original, target)
                print(target)
                continue
            if args.cutout_directory:
                with Image.open(args.cutout_directory / f"{artwork}.png") as edited:
                    if edited.size != size and artwork != COLORFUL_2027:
                        raise ValueError(f"Unexpected cutout dimensions: {artwork}")
                    with edited.getchannel("A") as generated:
                        # Remove near-zero haze and make the backdrop fully opaque;
                        # retain the generated contour's intermediate antialiasing.
                        if artwork == COLORFUL_2027:
                            # Align only the mask; preserve the supplied artwork's native canvas.
                            with generated.resize(size, Image.Resampling.LANCZOS) as aligned:
                                alpha = black_opening_alpha(source, aligned)
                        else:
                            alpha = (pine_cones_alpha(source, generated) if artwork == PINE_CONES else
                                     generated.point(lambda value: 0 if value < 16 else 255 if value > 240 else value))
                with alpha:
                    MASKS.mkdir(exist_ok=True)
                    alpha.save(mask_path)
            with Image.open(mask_path) as alpha:
                if alpha.mode != "L" or alpha.size != size:
                    raise ValueError(f"Unexpected alpha mask: {mask_path}")
                if artwork == PINE_CONES:
                    remove_black_matte(overlay, alpha)
                overlay.putalpha(alpha)
                overlay.save(target)
                print(target)


if __name__ == "__main__":
    main()
