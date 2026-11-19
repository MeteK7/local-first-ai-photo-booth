"""Versioned capture plans and customer directions for Multi-Photo Studio."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


MINI_SCENE_BEATS = ("Setup", "Action", "Reaction", "Ending")
SCULPTURE_POSITIONS = ("Left", "Center", "Right")
CreativePlan = BetweenFramesPlan | MotionStudyPlan | MiniScenePlan | TimeSculpturePlan
CapturePlan = SignatureStripPlan | CreativePlan

DEFAULT_PLAN = SignatureStripPlan()
LEGACY_STRIP_FILENAME = "classic-filmstrip.jpg"


class CaptureDirections(BaseModel):
    title: str
    introduction: str
    prompts: tuple[str, ...] = ()
    first_countdown: int = 3
    next_countdown: int = 3
    transfer_note: str | None = None
    manual_advance: bool = False


def capture_directions(plan: CapturePlan) -> CaptureDirections:
    if isinstance(plan, BetweenFramesPlan):
        prompts = ("Hold a calm expression.", "Change your gaze.", "Break into a laugh.")
        if plan.count == 2:
            prompts = (prompts[0], prompts[2])
        return CaptureDirections(
            title="Between Frames",
            introduction="Try a different expression or pose in each frame.",
            prompts=prompts if plan.guided else (),
        )
    if isinstance(plan, MotionStudyPlan):
        middle = {
            4: ("Begin the move.", "Reach the widest part of the move."),
            5: ("Begin the move.", "Move through the halfway point.", "Reach the widest part of the move."),
            6: ("Begin the move.", "Move through the halfway point.", "Reach the widest part of the move.",
                "Let the motion settle."),
        }
        return CaptureDirections(
            title="Motion Study",
            introduction="Pick a small move, like an arm sweep or a turn. Hold each pose until the shutter.",
            prompts=("Set your starting pose.", *middle[plan.count], "Hold your final pose."),
            next_countdown=2,
            transfer_note="Saving this frame. Get ready for the next cue.",
        )
    if isinstance(plan, MiniScenePlan):
        actions = ("Show us who you are.", "Make something happen.", "Show how you feel about it.", "Give the story an ending.")
        return CaptureDirections(
            title="Mini Scene", introduction="Tell a short story in four photos. Start each countdown when you’re ready.",
            prompts=tuple(f"{beat} · {action}" for beat, action in zip(MINI_SCENE_BEATS, actions, strict=True)),
            manual_advance=True,
        )
    if isinstance(plan, TimeSculpturePlan):
        return CaptureDirections(
            title="Time Sculpture",
            introduction="Keep the camera fixed. Start with an empty scene, then fit your entire pose inside each marked area.",
            prompts=("Empty scene · Step out of frame.", *(f"{position} · Step fully inside the highlighted area."
                       for position in SCULPTURE_POSITIONS)),
            first_countdown=4, next_countdown=5, manual_advance=True,
        )
    return CaptureDirections(title="Signature Strip", introduction="The camera counts down before each photo.")


def print_layout(plan: CapturePlan) -> StripLayout:
    return plan.layout if isinstance(plan, SignatureStripPlan) else StripLayout.GRID
