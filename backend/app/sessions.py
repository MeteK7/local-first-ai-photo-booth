from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import CheckConstraint, DateTime, String, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.filmstrip import dimensions, frame_boxes
from app.multi_photo import DEFAULT_PLAN, MAX_FRAMES, MIN_FRAMES, SignatureStripPlan, StripLayout
from app.security import issue_token, token_digest

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
COOKIE = "booth_customer"
LIFETIME = timedelta(minutes=30)


class State(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELED = "canceled"


class Experience(StrEnum):
    SINGLE = "single"
    FILMSTRIP = "filmstrip"


class BoothSession(Base):
    __tablename__ = "booth_sessions"
    __table_args__ = (
        CheckConstraint("state IN ('active', 'completed', 'canceled')", name="session_state"),
        CheckConstraint("(state = 'active') = (ended_at IS NULL)", name="session_end"),
        CheckConstraint("experience IN ('single', 'filmstrip')", name="session_experience"),
        CheckConstraint("multi_photo_plan IS NULL OR experience = 'filmstrip'", name="session_multi_photo_plan"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    access_digest: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[str] = mapped_column(String(12))
    experience: Mapped[str] = mapped_column(String(12), server_default="single")
    multi_photo_plan: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def signature_plan(self) -> SignatureStripPlan:
        return DEFAULT_PLAN if self.multi_photo_plan is None else SignatureStripPlan.model_validate(self.multi_photo_plan)

    def finish(self, target: State, now: datetime) -> None:
        if self.state != State.ACTIVE or target not in (State.COMPLETED, State.CANCELED):
            raise ValueError("Invalid session transition")
        self.state = target
        self.ended_at = now


class SessionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    state: State
    experience: Experience
    multi_photo_plan: SignatureStripPlan | None
    started_at: datetime
    expires_at: datetime
    ended_at: datetime | None


class FinishRequest(BaseModel):
    state: State


class StartRequest(BaseModel):
    experience: Experience = Experience.SINGLE
    multi_photo_plan: SignatureStripPlan | None = None

    @model_validator(mode="after")
    def validate_experience(self):
        if self.multi_photo_plan is not None and self.experience != Experience.FILMSTRIP:
            raise ValueError("A capture plan requires a Multi-Photo Studio session.")
        return self


def active_session(db, token: str | None, now: datetime, *, lock: bool = False):
    if not token:
        return None
    query = select(BoothSession).where(
        BoothSession.access_digest == token_digest(token),
        BoothSession.state == State.ACTIVE,
        BoothSession.expires_at > now,
    )
    return db.scalar(query.with_for_update() if lock else query)


@router.get("/current", response_model=SessionView | None)
def current(request: Request, booth_customer: str | None = Cookie(default=None)):
    with request.app.state.db() as db:
        return active_session(db, booth_customer, datetime.now(UTC))


@router.get("/multi-photo-studio")
def multi_photo_studio():
    return {
        "default_plan": DEFAULT_PLAN,
        "counts": list(range(MIN_FRAMES, MAX_FRAMES + 1)),
        "layouts": [
            {
                "id": layout,
                "name": name,
                "size": size,
                "width": dimensions(layout)[0],
                "height": dimensions(layout)[1],
                "frames": {
                    count: frame_boxes(SignatureStripPlan(count=count, layout=layout))
                    for count in range(MIN_FRAMES, MAX_FRAMES + 1)
                },
            }
            for layout, name, size in (
                (StripLayout.VERTICAL, "Vertical", "2 × 6 in"),
                (StripLayout.HORIZONTAL, "Horizontal", "6 × 2 in"),
                (StripLayout.GRID, "Grid", "6 × 4 in"),
            )
        ],
    }


@router.post("", response_model=SessionView, status_code=201)
def start(request: Request, response: Response, body: StartRequest | None = None,
          booth_customer: str | None = Cookie(default=None)):
    now = datetime.now(UTC)
    with request.app.state.db.begin() as db:
        existing = active_session(db, booth_customer, now, lock=True)
        if existing:
            response.status_code = 200
            return existing
        token = issue_token()
        plan = body.multi_photo_plan if body else None
        session = BoothSession(
            access_digest=token_digest(token), state=State.ACTIVE, started_at=now,
            expires_at=now + LIFETIME,
            experience=body.experience if body is not None else Experience.SINGLE,
            multi_photo_plan=plan.model_dump(mode="json") if plan is not None else None,
        )
        db.add(session)
        db.flush()
        response.set_cookie(
            COOKIE, token, httponly=True, samesite="strict", path="/api/sessions",
            max_age=int(LIFETIME.total_seconds()),
        )
        return session


@router.post("/current/finish", response_model=SessionView)
def finish(body: FinishRequest, request: Request, response: Response,
           booth_customer: str | None = Cookie(default=None)):
    if body.state not in (State.COMPLETED, State.CANCELED):
        raise HTTPException(422, "Choose a terminal session state.")
    now = datetime.now(UTC)
    with request.app.state.db.begin() as db:
        session = active_session(db, booth_customer, now, lock=True)
        if session is None:
            raise HTTPException(404, "There is no active session.")
        session.finish(body.state, now)
        response.delete_cookie(COOKIE, path="/api/sessions", httponly=True, samesite="strict")
        return session
