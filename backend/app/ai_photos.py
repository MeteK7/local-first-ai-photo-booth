"""Read-only access to saved results from the retired local preview."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.photos import OriginalPhoto, require_session, stored_file

router = APIRouter(prefix="/api/sessions/current/photos/ai", tags=["saved photo effects"])


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


def require_completed_effect(db, session_id: UUID, job_id: UUID) -> UUID:
    result = db.scalar(select(AIJob.id).join(OriginalPhoto, AIJob.original_id == OriginalPhoto.id).where(
        AIJob.id == job_id, AIJob.state == JobState.COMPLETED, OriginalPhoto.session_id == session_id,
    ))
    if result is None:
        raise HTTPException(404, "Photo result not found.")
    return result


def completed_file(job_id: UUID, request: Request, token: str | None):
    with request.app.state.db() as db:
        session = require_session(db, token)
        result = require_completed_effect(db, session.id, job_id)
    return stored_file(request, "ai-generated", result)


@router.get("/{job_id}/preview")
def preview(job_id: UUID, request: Request, booth_customer: str | None = Cookie(default=None)):
    return FileResponse(completed_file(job_id, request, booth_customer), media_type="image/jpeg")


@router.get("/{job_id}/download")
def download(job_id: UUID, request: Request, booth_customer: str | None = Cookie(default=None)):
    return FileResponse(completed_file(job_id, request, booth_customer), media_type="image/jpeg",
                        filename="photo-booth-effect.jpg")
