"""Rebuild transparent overlays from the original user-supplied artwork.

Usage: .venv/Scripts/python scripts/prepare-new-year-multi.py SOURCE_DIRECTORY
The originals remain untouched. Photo-window geometry lives in app.new_year_multi.
"""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageChops

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.multi_photo import NewYearTemplate
from app.new_year_multi import WINDOWS, artwork_path, artwork_size, window_mask

SOURCES = {
    NewYearTemplate.MIDNIGHT_MEMORIES: "ChatGPT Image Nov 23, 2026, 10_21_42 PM.png",
    NewYearTemplate.FRESH_CHAPTER: "ChatGPT Image Nov 23, 2026, 10_24_54 PM.png",
    NewYearTemplate.PARTY_AFTER_DARK: "ChatGPT Image Nov 23, 2026, 10_24_44 PM.png",
    NewYearTemplate.SPARKLE_SEASON: "ChatGPT Image Nov 23, 2026, 10_24_19 PM.png",
    NewYearTemplate.RADIANT_WELCOME: "Radiant Welcome 2027 Celebration Collage.png",
    NewYearTemplate.HELLO_2027: "Hello 2027 Celebration Collage.png",
    NewYearTemplate.GLITTERING_WELCOME: "Welcome 2027_ Glittering Celebration Collage.png",
    NewYearTemplate.WELCOME_CELEBRATION: "Welcome to the 2027 Celebration.png",
    NewYearTemplate.CHAMPAGNE_CHEERS: "Gemini_Generated_Image_98cchu98cchu98cc.jpg",
    NewYearTemplate.NEW_YEARS_EVE: "Gemini_Generated_Image_2lhvwg2lhvwg2lhv.jpg",
    NewYearTemplate.BURGUNDY_CELEBRATION: "Festive 2027 Burgundy New Year Frame.png",
    NewYearTemplate.RETRO_CONFETTI: "Gemini_Generated_Image_jo435jo435jo435j.jpg",
    NewYearTemplate.AURORA_CELEBRATION: "New Year 2027 Aurora Celebration.png",
}
SOFT_ALPHA_TEMPLATES = frozenset((NewYearTemplate.BURGUNDY_CELEBRATION,
                                  NewYearTemplate.RETRO_CONFETTI, NewYearTemplate.AURORA_CELEBRATION))
MASKS = Path(__file__).parent / "new-year-masks"
WHITE_OPENINGS = frozenset((NewYearTemplate.RADIANT_WELCOME, NewYearTemplate.HELLO_2027,
                           NewYearTemplate.GLITTERING_WELCOME, NewYearTemplate.WELCOME_CELEBRATION))


def protect_foreground(original: Image.Image, alpha: Image.Image) -> Image.Image:
    """Keep colored metal and dark foreground pixels at white-window cutout edges."""
    with original.convert("RGB") as rgb:
        red, green, blue = rgb.split()
        with red, green, blue, ImageChops.darker(red, green) as low_rg, \
                ImageChops.lighter(red, green) as high_rg, ImageChops.darker(low_rg, blue) as low, \
                ImageChops.lighter(high_rg, blue) as high, ImageChops.subtract(high, low) as chroma, \
                low.point(lambda value: 255 if value < 210 else 0) as dark, \
                chroma.point(lambda value: 255 if value > 25 else 0) as colored, \
                ImageChops.lighter(dark, colored) as foreground:
            return ImageChops.lighter(alpha, foreground)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_directory", type=Path)
    parser.add_argument("--template", action="append", type=NewYearTemplate, choices=list(NewYearTemplate))
    parser.add_argument("--cutout-directory", type=Path,
                        help="Import built-in imagegen edits named TEMPLATE.png as reusable alpha masks.")
    args = parser.parse_args()
    for template in args.template or SOURCES:
        source = args.source_directory / SOURCES[template]
        size = artwork_size(template)
        with Image.open(source) as original, original.convert("RGBA") as overlay, Image.new("L", size) as empty:
            if original.size != size:
                raise ValueError(f"Unexpected artwork dimensions: {source}")
            mask_path = MASKS / f"{template}.png"
            if args.cutout_directory:
                with Image.open(args.cutout_directory / f"{template}.png") as edited, \
                        edited.getchannel("A") as generated:
                    if template in SOFT_ALPHA_TEMPLATES:
                        # Keep the generated intermediate opacity: it carries the
                        # soft inner glow and shadows that blend over real photos.
                        # Near-opaque backdrop values are made opaque without
                        # discarding the faintest alpha values inside the frames.
                        with generated.point(lambda alpha: 255 if alpha >= 250 else alpha) as soft, \
                                soft.resize(size, Image.Resampling.LANCZOS) as alpha:
                            MASKS.mkdir(exist_ok=True)
                            alpha.save(mask_path)
                    else:
                        # The edited RGB is discarded: retain the supplied artwork exactly.
                        # Quantize the model's near-zero/near-opaque alpha before resampling
                        # so blank interiors are fully transparent and the backdrop is opaque.
                        with generated.point(lambda alpha: 0 if alpha < 128 else 255) as clean, \
                                clean.resize(size, Image.Resampling.LANCZOS) as resized:
                            MASKS.mkdir(exist_ok=True)
                            with (protect_foreground(original, resized) if template in WHITE_OPENINGS else resized.copy()) as alpha:
                                alpha.save(mask_path)
            if mask_path.is_file():
                with Image.open(mask_path) as alpha:
                    if alpha.mode != "L" or alpha.size != size:
                        raise ValueError(f"Unexpected alpha mask: {mask_path}")
                    overlay.putalpha(alpha)
                    overlay.save(artwork_path(template))
                print(artwork_path(template))
                continue
            cutouts = empty.copy()
            for window in WINDOWS[template]:
                with window_mask(window, size) as hole:
                    combined = ImageChops.lighter(cutouts, hole)
                cutouts.close()
                cutouts = combined
            with cutouts, ImageChops.invert(cutouts) as alpha:
                overlay.putalpha(alpha)
                overlay.save(artwork_path(template))
        print(artwork_path(template))


if __name__ == "__main__":
    main()
