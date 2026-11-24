"""Shared offline catalogs and localization for server-rendered surfaces."""

import json
import re
from functools import lru_cache
from typing import Literal

from fastapi import HTTPException
from PIL import ImageFont
from pydantic import BaseModel

from app.config import ROOT

Locale = Literal["en", "tr"]
DEFAULT_LOCALE: Locale = "en"
LOCALES = ("en", "tr")

CATALOGS = {locale: json.loads((ROOT / "i18n" / f"{locale}.json").read_text(encoding="utf-8"))
            for locale in LOCALES}
LEGACY_KEYS = {text: key for key, text in CATALOGS[DEFAULT_LOCALE].items()
               if key.startswith("messages.")}
PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*}}")
QUALITY = re.compile(r"q=(0(?:\.\d{0,3})?|1(?:\.0{0,3})?)", re.IGNORECASE)
FONT = ROOT / "backend" / "app" / "assets" / "NotoSans.ttf"


def translate(key: str, locale: Locale = DEFAULT_LOCALE, **params: str | int) -> str:
    return PLACEHOLDER.sub(lambda match: str(params[match.group(1)]), CATALOGS[locale][key])


class UiMessage(BaseModel):
    key: str
    params: dict[str, str | int] | None = None


class LocalizedError(HTTPException):
    def __init__(self, status: int, key: str, **params: str | int) -> None:
        self.messages = [UiMessage(key=key, params=params or None)]
        super().__init__(status, translate(key, **params))


def legacy_messages(detail: str | None, fallback: str | None = None) -> list[UiMessage]:
    key = LEGACY_KEYS.get(detail) if detail is not None else None
    key = key or fallback
    return [UiMessage(key=key)] if key else []


def camera_messages(detail: str | None) -> list[UiMessage]:
    if not detail:
        return []
    known = legacy_messages(detail)
    if known:
        return known
    # Nikon can return several complete setup instructions in one legacy detail.
    keys = [LEGACY_KEYS.get(part) for part in re.split(r"(?<=\.) ", detail)]
    if all(key and key.startswith("messages.camera.") for key in keys):
        return [UiMessage(key=key) for key in keys if key is not None]
    return [UiMessage(key="messages.cameraUnavailable")]


def phone_locale(accept_language: str) -> Locale:
    preferences: dict[str, tuple[float, int]] = {}
    for index, entry in enumerate(accept_language.split(",")):
        tag, *params = entry.strip().lower().split(";")
        quality = QUALITY.fullmatch(params[0].strip()) if len(params) == 1 else None
        if params and quality is None:
            continue
        base = tag.strip().partition("-")[0]
        preference = (float(quality.group(1)) if quality else 1.0, -index)
        preferences[base] = max(preferences.get(base, (0.0, -len(accept_language))), preference)
    wildcard = preferences.get("*", (0.0, 0))
    best: Locale = max(LOCALES, key=lambda locale: preferences.get(locale, wildcard))
    return best if preferences.get(best, wildcard)[0] > 0 else DEFAULT_LOCALE


@lru_cache(maxsize=16)
def artwork_font(locale: Locale, size: int) -> ImageFont.FreeTypeFont:
    if locale == "tr":
        return ImageFont.truetype(FONT, size=size)
    return ImageFont.load_default(size=size)
