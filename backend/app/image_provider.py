"""Image transformation boundary and the offline preview processor."""

from io import BytesIO
from typing import Protocol

from PIL import Image, ImageOps

IMAGE_LIMIT = 32 * 1024 * 1024
PREVIEW_SIZE = (1536, 1536)


class ImageProvider(Protocol):
    key: str
    label: str
    sends_photo: bool
    privacy_url: str | None

    def transform(self, jpeg: bytes, prompt: str) -> bytes:
        """Return a JPEG. An external implementation must bound its request time."""
        ...


def prepare_input(original: bytes) -> bytes:
    """Resize and rebuild the JPEG from pixels so input metadata stays local."""
    with Image.open(BytesIO(original), formats=("JPEG",)) as image, BytesIO() as output:
        ImageOps.exif_transpose(image, in_place=True)
        with image.convert("RGB") as rgb:
            rgb.thumbnail(PREVIEW_SIZE, Image.Resampling.LANCZOS)
            rgb.info.clear()
            rgb.save(output, "JPEG", quality=92)
        return output.getvalue()


class LocalPreviewProvider:
    key = "local-preview"
    label = "Local preview"
    sends_photo = False
    privacy_url = None

    def transform(self, jpeg: bytes, _prompt: str) -> bytes:
        with Image.open(BytesIO(jpeg), formats=("JPEG",)) as image, BytesIO() as output:
            with ImageOps.grayscale(image) as gray, ImageOps.autocontrast(gray) as contrast:
                with ImageOps.colorize(contrast, "#182d40", "#ffdfb4") as tone:
                    with Image.blend(image, tone, .58) as graded:
                        graded.save(output, "JPEG", quality=94)
            return output.getvalue()


def select_provider(mode: str) -> ImageProvider | None:
    return LocalPreviewProvider() if mode == "preview" else None
