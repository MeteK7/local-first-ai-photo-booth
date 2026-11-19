"""Multi-Photo Studio configuration and the Signature Strip capture plan."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MIN_FRAMES = 2
MAX_FRAMES = 6
DEFAULT_FRAMES = 3


class StripLayout(StrEnum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"
    GRID = "grid"


class SignatureStripPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    experience: Literal["signature-strip"] = "signature-strip"
    version: Literal[1] = 1
    count: int = Field(default=DEFAULT_FRAMES, ge=MIN_FRAMES, le=MAX_FRAMES, strict=True)
    layout: StripLayout = StripLayout.VERTICAL


DEFAULT_PLAN = SignatureStripPlan()
SIGNATURE_STRIP_FILENAME = "signature-strip.jpg"
LEGACY_STRIP_FILENAME = "classic-filmstrip.jpg"
