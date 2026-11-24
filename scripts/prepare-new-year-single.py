"""Build single-shoot overlays while retaining the supplied artwork's RGB pixels.

Usage: .venv/Scripts/python scripts/prepare-new-year-single.py SOURCE_DIRECTORY
Use --cutout-directory to import imagegen PNGs named ARTWORK_ID.png as alpha masks.
The checked-in masks allow rebuilding without calling an image service.
The Cozy Winter PNG is copied unchanged, including its native translucent glow.
"""

import argparse
from pathlib import Path
from shutil import copyfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MASKS = Path(__file__).with_name("new-year-single-masks")
SOURCES = {
    "new-year-bright-blue-landscape": "Bright Blue New Year Photo Frame.png",
    "new-year-vibrant-2027-landscape": "Vibrant 2027 New Year Celebration Frame.png",
    "new-year-cozy-winter-landscape": "Happy New Year 2027 Frame.png",
}
SIZE = (1536, 1024)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_directory", type=Path)
    parser.add_argument("--cutout-directory", type=Path)
    args = parser.parse_args()
    for artwork, filename in SOURCES.items():
        original = args.source_directory / filename
        target = ROOT / "backend" / "app" / "assets" / f"{artwork}.png"
        with Image.open(original) as source, source.convert("RGBA") as overlay:
            if source.size != SIZE:
                raise ValueError(f"Unexpected artwork dimensions: {filename}")
            mask_path = MASKS / f"{artwork}.png"
            if artwork == "new-year-cozy-winter-landscape":
                if source.mode != "RGBA":
                    raise ValueError("Cozy Winter must retain the original RGBA transparency")
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
                    if edited.size != SIZE:
                        raise ValueError(f"Unexpected cutout dimensions: {artwork}")
                    with edited.getchannel("A") as generated:
                        # Remove near-zero haze and make the backdrop fully opaque;
                        # retain the generated contour's intermediate antialiasing.
                        alpha = generated.point(lambda value: 0 if value < 16 else 255 if value > 240 else value)
                with alpha:
                    MASKS.mkdir(exist_ok=True)
                    alpha.save(mask_path)
            with Image.open(mask_path) as alpha:
                if alpha.mode != "L" or alpha.size != SIZE:
                    raise ValueError(f"Unexpected alpha mask: {mask_path}")
                overlay.putalpha(alpha)
                overlay.save(target)
                print(target)


if __name__ == "__main__":
    main()
