import os
from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID

MEDIA_AREAS = ("originals", "processed", "ai-generated", "temporary")


def prepare_storage(root: Path) -> None:
    for area in MEDIA_AREAS:
        root.joinpath(area).mkdir(parents=True, exist_ok=True)


def asset_path(root: Path, area: str, asset_id: UUID) -> Path:
    if area not in MEDIA_AREAS or not isinstance(asset_id, UUID):
        raise ValueError("Unsupported storage area")
    base = root.resolve()
    directory = (base / area).resolve()
    target = (directory / f"{asset_id}.jpg").resolve()
    if directory != base / area or target.parent != directory:
        raise ValueError("Asset path escapes the storage area")
    return target


def jpeg_dimensions(image: bytes) -> tuple[int, int]:
    if not (image.startswith(b"\xff\xd8") and image.endswith(b"\xff\xd9")):
        raise ValueError("A complete JPEG is required")
    frame_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    offset = 2
    while offset + 4 < len(image) and image[offset] == 0xFF:
        while offset + 4 < len(image) and image[offset] == 0xFF:
            offset += 1
        if offset + 7 >= len(image):
            break
        marker = image[offset]
        length = int.from_bytes(image[offset + 1:offset + 3], "big")
        if length < 2 or offset + 1 + length > len(image):
            break
        if marker in frame_markers and length >= 8:
            height = int.from_bytes(image[offset + 4:offset + 6], "big")
            width = int.from_bytes(image[offset + 6:offset + 8], "big")
            if width and height:
                return width, height
        if marker == 0xDA:  # Start of scan. The dimensions precede the scan data.
            break
        offset += 1 + length
    raise ValueError("JPEG dimensions are missing")


def save_original(root: Path, photo_id: UUID, jpeg: bytes) -> None:
    save_jpeg(root, "originals", photo_id, jpeg)


def save_jpeg(root: Path, area: str, photo_id: UUID, jpeg: bytes) -> None:
    target = asset_path(root, area, photo_id)
    temp = None
    try:
        with NamedTemporaryFile(dir=target.parent, suffix=".partial", delete=False) as stream:
            temp = Path(stream.name)
            stream.write(jpeg)
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(target)
    finally:
        if temp is not None:
            with suppress(FileNotFoundError):
                temp.unlink()
