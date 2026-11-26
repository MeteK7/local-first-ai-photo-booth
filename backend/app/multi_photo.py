"""Versioned capture plans and customer directions for Multi-Photo Studio."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.i18n import translate

MIN_FRAMES = 2
MAX_FRAMES = 6
DEFAULT_FRAMES = 3


class StripLayout(StrEnum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"
    GRID = "grid"


class MotionStudyLayout(StrEnum):
    CONTACT_STACK = "contact-stack"
    MATCH_CUT = "match-cut"
    ASCENDING_CUT = "ascending-cut"

    @property
    def counts(self) -> tuple[int, ...]:
        return (4, 5, 6) if self == MotionStudyLayout.ASCENDING_CUT else (4,)


class SignatureStripPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    experience: Literal["signature-strip"] = "signature-strip"
    version: Literal[1] = 1
    count: int = Field(default=DEFAULT_FRAMES, ge=MIN_FRAMES, le=MAX_FRAMES, strict=True)
    layout: StripLayout = StripLayout.VERTICAL


class BetweenFramesPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    experience: Literal["between-frames"]
    version: Literal[1] = 1
    count: int = Field(default=2, ge=2, le=3, strict=True)
    guided: bool = Field(default=True, strict=True)


class MotionStudyPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    experience: Literal["motion-study"]
    version: Literal[1] = 1
    count: int = Field(default=4, ge=4, le=MAX_FRAMES, strict=True)
    layout: MotionStudyLayout | None = Field(default=None, exclude_if=lambda layout: layout is None)

    @model_validator(mode="after")
    def validate_layout_count(self):
        if self.layout is not None and self.count not in self.layout.counts:
            raise ValueError("This Motion Study layout requires four photos.")
        return self


class MiniScenePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    experience: Literal["mini-scene"]
    version: Literal[1] = 1
    count: Literal[4] = 4


class TimeSculpturePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    experience: Literal["time-sculpture"]
    version: Literal[1] = 1
    count: Literal[4] = 4


class NewYearTemplate(StrEnum):
    MIDNIGHT_MEMORIES = "midnight-memories"
    FRESH_CHAPTER = "fresh-chapter"
    PARTY_AFTER_DARK = "party-after-dark"
    SPARKLE_SEASON = "sparkle-season"
    RADIANT_WELCOME = "radiant-welcome"
    HELLO_2027 = "hello-2027"
    GLITTERING_WELCOME = "glittering-welcome"
    WELCOME_CELEBRATION = "welcome-celebration"
    CHAMPAGNE_CHEERS = "champagne-cheers"
    NEW_YEARS_EVE = "new-years-eve"
    BURGUNDY_CELEBRATION = "burgundy-celebration"
    RETRO_CONFETTI = "retro-confetti"
    AURORA_CELEBRATION = "aurora-celebration"

    @property
    def count(self) -> int:
        return 5 if self == NewYearTemplate.FRESH_CHAPTER else 4


class NewYearPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    experience: Literal["new-year"] = "new-year"
    version: Literal[1] = 1
    template: NewYearTemplate
    count: int = Field(default=4, ge=4, le=5, strict=True)

    @model_validator(mode="after")
    def validate_template_count(self):
        if self.count != self.template.count:
            raise ValueError("The number of photos must match the New Year template.")
        return self


MINI_SCENE_BEATS = ("Setup", "Action", "Reaction", "Ending")
SCULPTURE_POSITIONS = ("Left", "Center", "Right")
CreativePlan = BetweenFramesPlan | MotionStudyPlan | MiniScenePlan | TimeSculpturePlan
CapturePlan = SignatureStripPlan | CreativePlan | NewYearPlan

DEFAULT_PLAN = SignatureStripPlan()
LEGACY_STRIP_FILENAME = "classic-filmstrip.jpg"


class CaptureDirections(BaseModel):
    title: str
    introduction: str
    title_key: str
    introduction_key: str
    prompts: tuple[str, ...] = ()
    prompt_keys: tuple[str, ...] = ()
    first_countdown: int = 3
    next_countdown: int = 3
    transfer_note: str | None = None
    transfer_key: str | None = None
    manual_advance: bool = False


def directions(experience: str, prompts: tuple[str, ...] = (), *, transfer: str | None = None,
               first: int = 3, next_countdown: int = 3, manual: bool = False) -> CaptureDirections:
    title = f"studio.experience.{experience}.name"
    intro = "session.countdownHint" if experience == "signature-strip" else f"studio.experience.{experience}.intro"
    return CaptureDirections(
        title=translate(title), introduction=translate(intro), title_key=title, introduction_key=intro,
        prompts=tuple(translate(key) for key in prompts), prompt_keys=prompts,
        transfer_note=translate(transfer) if transfer else None, transfer_key=transfer,
        first_countdown=first, next_countdown=next_countdown, manual_advance=manual,
    )


def capture_directions(plan: CapturePlan) -> CaptureDirections:
    if isinstance(plan, NewYearPlan):
        return directions(plan.experience)
    if isinstance(plan, BetweenFramesPlan):
        poses = ("calm", "gaze", "laugh") if plan.count == 3 else ("calm", "laugh")
        return directions(plan.experience, tuple(f"studio.between.{pose}" for pose in poses) if plan.guided else ())
    if isinstance(plan, MotionStudyPlan):
        middle = {
            4: ("begin", "widest"),
            5: ("begin", "halfway", "widest"),
            6: ("begin", "halfway", "widest", "settle"),
        }
        return directions(
            plan.experience, tuple(f"studio.motion.{pose}" for pose in ("start", *middle[plan.count], "final")),
            next_countdown=2, transfer="studio.motion.transfer",
        )
    if isinstance(plan, MiniScenePlan):
        return directions(
            plan.experience, tuple(f"studio.scene.{beat.lower()}" for beat in MINI_SCENE_BEATS), manual=True,
        )
    if isinstance(plan, TimeSculpturePlan):
        return directions(
            plan.experience, tuple(f"studio.sculpture.{position.lower()}" for position in ("Empty", *SCULPTURE_POSITIONS)),
            first=4, next_countdown=5, manual=True,
        )
    return directions(plan.experience)


def print_layout(plan: CapturePlan) -> StripLayout:
    return plan.layout if isinstance(plan, SignatureStripPlan) else StripLayout.GRID
