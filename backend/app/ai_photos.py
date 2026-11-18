"""Confine transformation jobs and generated media to their owning session."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from io import BytesIO
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.image_provider import IMAGE_LIMIT, ImageProvider, prepare_input
from app.media import asset_path, jpeg_dimensions, save_jpeg
from app.photos import OriginalPhoto, require_result, require_session, stored_file
from app.sessions import BoothSession, State

router = APIRouter(prefix="/api/sessions/current/photos/ai", tags=["photo transformations"])
log = logging.getLogger("uvicorn.error")
STALE_AFTER = timedelta(minutes=5)


class JobState(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELED = "canceled"


class AITemplate(Base):
    __tablename__ = "ai_templates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(240))
    prompt: Mapped[str]
    enabled: Mapped[bool]


class AIJob(Base):
    __tablename__ = "ai_jobs"
    __table_args__ = (
        UniqueConstraint("original_id", "template_id", "provider", name="ai_job_one_result"),
        CheckConstraint(
            "state IN ('queued', 'processing', 'completed', 'failed', 'interrupted', 'canceled')",
            name="ai_job_state",
        ),
        CheckConstraint(
            "(state = 'completed' AND width IS NOT NULL AND height IS NOT NULL AND byte_size IS NOT NULL)"
            " OR (state <> 'completed' AND width IS NULL AND height IS NULL AND byte_size IS NULL)",
            name="ai_job_result",
        ),
        Index("ix_ai_jobs_provider_state_updated_at", "provider", "state", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    original_id: Mapped[UUID] = mapped_column(ForeignKey("original_photos.id"))
    template_id: Mapped[str] = mapped_column(ForeignKey("ai_templates.id"))
    prompt: Mapped[str]
    provider: Mapped[str] = mapped_column(String(64))
    sends_photo: Mapped[bool]
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(16))
    detail: Mapped[str]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    byte_size: Mapped[int | None]
    width: Mapped[int | None]
    height: Mapped[int | None]


class TransformRequest(BaseModel):
    asset_id: UUID
    template_id: str
    consent: StrictBool


class JobView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_id: str
    state: JobState
    detail: str


class TemplateView(BaseModel):
    id: str
    name: str
    description: str
    job: JobView | None


class ProviderView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    label: str
    sends_photo: bool
    privacy_url: str | None


class TransformOptions(BaseModel):
    provider: ProviderView | None
    templates: list[TemplateView]


@router.get("", response_model=TransformOptions)
def options(asset_id: UUID, request: Request, booth_customer: str | None = Cookie(default=None)):
    provider = request.app.state.image_provider
    with request.app.state.db() as db:
        session = require_session(db, booth_customer)
        require_result(db, session.id, asset_id, "original")
        if provider is None:
            return TransformOptions(provider=None, templates=[])
        templates = db.scalars(select(AITemplate).where(AITemplate.enabled).order_by(AITemplate.name))
        jobs = {job.template_id: job for job in db.scalars(
            select(AIJob).where(AIJob.original_id == asset_id, AIJob.provider == provider.key)
        )}
        return TransformOptions(
            provider=ProviderView.model_validate(provider),
            templates=[TemplateView(
                id=template.id, name=template.name, description=template.description,
                job=JobView.model_validate(jobs[template.id]) if template.id in jobs else None,
            ) for template in templates],
        )


@router.post("", response_model=JobView, status_code=202)
def start_transform(body: TransformRequest, request: Request, response: Response,
                    booth_customer: str | None = Cookie(default=None)):
    with request.app.state.db.begin() as db:
        session = require_session(db, booth_customer, lock=True)
        require_result(db, session.id, body.asset_id, "original")
        if not body.consent:
            raise HTTPException(422, "Confirm your consent to start processing this photo.")
        provider = request.app.state.image_provider
        if provider is None:
            raise HTTPException(503, "Photo transformations are disabled on this booth.")
        template = db.get(AITemplate, body.template_id)
        if template is None or not template.enabled:
            raise HTTPException(404, "This photo effect is unavailable.")
        job = db.scalar(select(AIJob).where(
            AIJob.original_id == body.asset_id, AIJob.template_id == template.id, AIJob.provider == provider.key,
        ))
        if job is not None and job.state != JobState.FAILED:
            response.status_code = 200
            return job
        stored_file(request, "originals", body.asset_id)
        if job is None:
            job = AIJob(id=uuid4(), original_id=body.asset_id, template_id=template.id, provider=provider.key)
            db.add(job)
        now = datetime.now(UTC)
        job.prompt, job.sends_photo, job.consented_at = template.prompt, provider.sends_photo, now
        job.state, job.detail, job.updated_at = JobState.QUEUED, "Waiting to process your photo.", now
        return job


def completed_file(job_id: UUID, request: Request, token: str | None):
    with request.app.state.db() as db:
        session = require_session(db, token)
        result = db.scalar(select(AIJob.id).join(OriginalPhoto, AIJob.original_id == OriginalPhoto.id).where(
            AIJob.id == job_id, AIJob.state == JobState.COMPLETED, OriginalPhoto.session_id == session.id,
        ))
    if result is None:
        raise HTTPException(404, "Photo result not found.")
    return stored_file(request, "ai-generated", result)


@router.get("/{job_id}/preview")
def preview(job_id: UUID, request: Request, booth_customer: str | None = Cookie(default=None)):
    return FileResponse(completed_file(job_id, request, booth_customer), media_type="image/jpeg")


@router.get("/{job_id}/download")
def download(job_id: UUID, request: Request, booth_customer: str | None = Cookie(default=None)):
    return FileResponse(completed_file(job_id, request, booth_customer), media_type="image/jpeg",
                        filename="photo-booth-effect.jpg")


def claim_job(sessions, provider: ImageProvider) -> AIJob | None:
    now = datetime.now(UTC)
    with sessions.begin() as db:
        job = db.scalar(select(AIJob).where(
            AIJob.provider == provider.key,
            (AIJob.state == JobState.QUEUED) | (
                (AIJob.state == JobState.PROCESSING) & (AIJob.updated_at < now - STALE_AFTER)
            ),
        ).order_by(AIJob.updated_at).limit(1).with_for_update(skip_locked=True))
        if job is None:
            return None
        job.updated_at = now
        if job.state == JobState.PROCESSING:
            job.state, job.detail = JobState.INTERRUPTED, "Processing was interrupted. Your original is available."
            return None
        original = db.get(OriginalPhoto, job.original_id)
        session = db.get(BoothSession, original.session_id) if original else None
        if (session is None or session.state != State.ACTIVE or session.expires_at <= now
                or job.sends_photo != provider.sends_photo):
            job.state, job.detail = JobState.CANCELED, "Processing was canceled before it started."
            return None
        job.state, job.detail = JobState.PROCESSING, "Processing your photo…"
        return job


def run_job(settings, sessions, provider: ImageProvider) -> None:
    job = claim_job(sessions, provider)
    if job is None:
        return
    sending = False
    result = None
    try:
        original = asset_path(settings.data_root, "originals", job.original_id)
        if original.stat().st_size > IMAGE_LIMIT:
            raise ValueError("Original exceeds the processing size limit")
        cleaned = prepare_input(original.read_bytes())
        sending = provider.sends_photo
        jpeg = provider.transform(cleaned, job.prompt)
        if len(jpeg) > IMAGE_LIMIT:
            raise ValueError("Result exceeds the processing size limit")
        width, height = jpeg_dimensions(jpeg)
        with Image.open(BytesIO(jpeg), formats=("JPEG",)) as image:
            image.load()
        save_jpeg(settings.data_root, "ai-generated", job.id, jpeg)
        result = (len(jpeg), width, height)
        state, detail = JobState.COMPLETED, "Your photo effect is ready."
    except Exception as exc:
        log.warning("Photo effect job %s failed (%s).", job.id, type(exc).__name__)
        state = JobState.INTERRUPTED if sending else JobState.FAILED
        detail = "The effect could not be completed. Your original is available."
    with sessions.begin() as db:
        current = db.get(AIJob, job.id, with_for_update=True)
        if current is not None and current.state == JobState.PROCESSING and current.updated_at == job.updated_at:
            current.state, current.detail, current.updated_at = state, detail, datetime.now(UTC)
            if result is not None:
                current.byte_size, current.width, current.height = result


@asynccontextmanager
async def ai_worker(settings, sessions, provider: ImageProvider | None):
    if provider is None:
        yield
        return
    stopped = asyncio.Event()

    async def run():
        while not stopped.is_set():
            try:
                await asyncio.to_thread(run_job, settings, sessions, provider)
            except SQLAlchemyError as exc:
                log.warning("Could not update the photo effect queue (%s).", type(exc).__name__)
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
