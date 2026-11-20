"""Render local Creative Studio JPEGs and scope them to the original's session."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, computed_field
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column

from app.ai_photos import AIJob
from app.creative_renderers import CATALOG, IMAGE_LIMIT, render
from app.db import Base
from app.i18n import DEFAULT_LOCALE, Locale, UiMessage, legacy_messages
from app.media import asset_path, jpeg_dimensions, save_jpeg
from app.photos import OriginalPhoto, require_result, require_session, stored_file
from app.sessions import BoothSession, Experience, State

router = APIRouter(prefix="/api/sessions/current/photos/creative", tags=["Creative Studio"])
log = logging.getLogger("uvicorn.error")
STALE_AFTER = timedelta(minutes=5)


class RenderState(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class CreativeResult(Base):
    __tablename__ = "creative_results"
    __table_args__ = (
        UniqueConstraint("original_id", "treatment", "version", name="creative_result_one_version"),
        CheckConstraint("state IN ('queued', 'processing', 'completed', 'failed', 'canceled')",
                        name="creative_result_state"),
        CheckConstraint(
            "(state = 'completed' AND width IS NOT NULL AND height IS NOT NULL AND byte_size IS NOT NULL)"
            " OR (state <> 'completed' AND width IS NULL AND height IS NULL AND byte_size IS NULL)",
            name="creative_result_file",
        ),
        Index("ix_creative_results_state_updated_at", "state", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    original_id: Mapped[UUID] = mapped_column(ForeignKey("original_photos.id"))
    treatment: Mapped[str] = mapped_column(String(40))
    version: Mapped[int]
    state: Mapped[str] = mapped_column(String(16))
    detail: Mapped[str]
    render_locale: Mapped[Locale] = mapped_column(String(2), server_default=DEFAULT_LOCALE)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    byte_size: Mapped[int | None]
    width: Mapped[int | None]
    height: Mapped[int | None]


class RenderRequest(BaseModel):
    asset_id: UUID
    treatment: str
    locale: Locale = DEFAULT_LOCALE


class RenderView(BaseModel):
    id: UUID
    kind: Literal["creative", "effect"]
    state: RenderState
    detail: str

    @computed_field
    @property
    def messages(self) -> list[UiMessage]:
        return legacy_messages(self.detail, f"messages.creative.{self.state}")


class TreatmentView(BaseModel):
    id: str
    name: str
    description: str
    result: RenderView | None


def result_view(result: CreativeResult) -> RenderView:
    return RenderView(id=result.id, kind="creative", state=result.state, detail=result.detail)


def classic_result(db, asset_id: UUID, request: Request) -> RenderView | None:
    legacy = db.scalar(select(AIJob.id).where(
        AIJob.original_id == asset_id, AIJob.template_id == "cinematic-portrait",
        AIJob.provider == "local-preview", AIJob.state == "completed",
    ))
    if legacy is not None and asset_path(request.app.state.settings.data_root, "ai-generated", legacy).is_file():
        return RenderView(id=legacy, kind="effect", state=RenderState.COMPLETED, detail="Your treatment is ready.")
    return None


def studio_session(db, token: str | None, *, lock: bool = False):
    session = require_session(db, token, lock=lock)
    if session.experience != Experience.SINGLE:
        raise HTTPException(404, "Creative Studio is available for single photos.")
    return session


@router.get("", response_model=list[TreatmentView])
def options(asset_id: UUID, request: Request, booth_customer: str | None = Cookie(default=None)):
    with request.app.state.db() as db:
        session = studio_session(db, booth_customer)
        require_result(db, session.id, asset_id, "original")
        results = {
            item.treatment: result_view(item)
            for item in db.scalars(select(CreativeResult).where(CreativeResult.original_id == asset_id))
            if item.treatment in CATALOG and item.version == CATALOG[item.treatment].version
        }
        if "classic-filter" not in results:
            legacy = classic_result(db, asset_id, request)
            if legacy:
                results["classic-filter"] = legacy
        return [TreatmentView(id=key, name=item.name, description=item.description, result=results.get(key))
                for key, item in CATALOG.items()]


@router.post("", response_model=RenderView, status_code=202)
def start_render(body: RenderRequest, request: Request, response: Response,
                 booth_customer: str | None = Cookie(default=None)):
    with request.app.state.db.begin() as db:
        session = studio_session(db, booth_customer, lock=True)
        require_result(db, session.id, body.asset_id, "original")
        treatment = CATALOG.get(body.treatment)
        if treatment is None:
            raise HTTPException(404, "This treatment is unavailable.")
        result = db.scalar(select(CreativeResult).where(
            CreativeResult.original_id == body.asset_id, CreativeResult.treatment == body.treatment,
            CreativeResult.version == treatment.version,
        ))
        if result is not None and result.state != RenderState.FAILED:
            response.status_code = 200
            return result_view(result)
        if result is None and body.treatment == "classic-filter":
            legacy = classic_result(db, body.asset_id, request)
            if legacy:
                response.status_code = 200
                return legacy
        stored_file(request, "originals", body.asset_id)
        if result is None:
            result = CreativeResult(id=uuid4(), original_id=body.asset_id, treatment=body.treatment,
                                    version=treatment.version)
            db.add(result)
        result.state = RenderState.QUEUED
        result.render_locale = body.locale
        result.detail = "Waiting to prepare your photo."
        result.updated_at = datetime.now(UTC)
        return result_view(result)


def creative_owner_query(result_id: UUID):
    return select(OriginalPhoto.session_id).join(CreativeResult, CreativeResult.original_id == OriginalPhoto.id).where(
        CreativeResult.id == result_id, CreativeResult.state == RenderState.COMPLETED,
    )


def require_creative_result(db, session_id: UUID, result_id: UUID) -> UUID:
    if db.scalar(creative_owner_query(result_id).where(OriginalPhoto.session_id == session_id)) is None:
        raise HTTPException(404, "Photo result not found.")
    return result_id


def completed_file(result_id: UUID, request: Request, token: str | None):
    with request.app.state.db() as db:
        session = studio_session(db, token)
        require_creative_result(db, session.id, result_id)
    return stored_file(request, "processed", result_id)


@router.get("/{result_id}/preview")
def preview(result_id: UUID, request: Request, booth_customer: str | None = Cookie(default=None)):
    return FileResponse(completed_file(result_id, request, booth_customer), media_type="image/jpeg")


@router.get("/{result_id}/download")
def download(result_id: UUID, request: Request, booth_customer: str | None = Cookie(default=None)):
    return FileResponse(completed_file(result_id, request, booth_customer), media_type="image/jpeg",
                        filename="creative-studio.jpg")


def claim_result(sessions) -> CreativeResult | None:
    now = datetime.now(UTC)
    with sessions.begin() as db:
        result = db.scalar(select(CreativeResult).where(or_(
            CreativeResult.state == RenderState.QUEUED,
            (CreativeResult.state == RenderState.PROCESSING) & (CreativeResult.updated_at < now - STALE_AFTER),
        )).order_by(CreativeResult.updated_at, CreativeResult.id).limit(1).with_for_update(skip_locked=True))
        if result is None:
            return None
        result.updated_at = now
        if result.state == RenderState.PROCESSING:
            result.state, result.detail = RenderState.FAILED, "Processing was interrupted. You can try again."
            return None
        original = db.get(OriginalPhoto, result.original_id)
        session = db.get(BoothSession, original.session_id)
        if session.state != State.ACTIVE or session.expires_at <= now:
            result.state, result.detail = RenderState.CANCELED, "The photo session ended."
            return None
        result.state, result.detail = RenderState.PROCESSING, "Preparing your photo…"
        return result


def run_render(settings, sessions) -> None:
    result = claim_result(sessions)
    if result is None:
        return
    dimensions = None
    try:
        path = asset_path(settings.data_root, "originals", result.original_id)
        if path.stat().st_size > IMAGE_LIMIT:
            raise ValueError("Original exceeds the processing limit")
        jpeg = render(result.treatment, result.version, path.read_bytes(), result.original_id, result.render_locale)
        dimensions = jpeg_dimensions(jpeg)
        save_jpeg(settings.data_root, "processed", result.id, jpeg)
        state, detail = RenderState.COMPLETED, "Your treatment is ready."
    except Exception as exc:
        state, detail = RenderState.FAILED, "This treatment could not be prepared. Your original is available."
        log.warning("Creative Studio result %s failed (%s).", result.id, type(exc).__name__)
    with sessions.begin() as db:
        current = db.get(CreativeResult, result.id, with_for_update=True)
        if current and current.state == RenderState.PROCESSING and current.updated_at == result.updated_at:
            current.state, current.detail, current.updated_at = state, detail, datetime.now(UTC)
            if state == RenderState.COMPLETED:
                current.width, current.height = dimensions
                current.byte_size = len(jpeg)


@asynccontextmanager
async def creative_worker(settings, sessions):
    stopped = asyncio.Event()

    async def run():
        while not stopped.is_set():
            try:
                await asyncio.to_thread(run_render, settings, sessions)
            except SQLAlchemyError as exc:
                log.warning("Could not update the Creative Studio queue (%s).", type(exc).__name__)
            try:
                await asyncio.wait_for(stopped.wait(), timeout=1)
            except TimeoutError:
                pass

    task = asyncio.create_task(run())
    try:
        yield
    finally:
        stopped.set()
        await task
