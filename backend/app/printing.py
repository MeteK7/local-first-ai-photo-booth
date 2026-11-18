"""One-copy local print jobs and the Windows spooler adapter."""

import asyncio
import json
import logging
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column

from app.config import ROOT, Settings
from app.db import Base
from app.media import asset_path
from app.photos import ResultKind, require_result, require_session, stored_file

router = APIRouter(prefix="/api/sessions/current/photos/print-jobs", tags=["printing"])
log = logging.getLogger("uvicorn.error")
SUBMISSION_TIMEOUT = 25
RECOVERY_DELAY = timedelta(seconds=2 * SUBMISSION_TIMEOUT)
QUEUED_DETAIL = "Waiting to send one copy to the printer."
UNCERTAIN_DETAIL = "Check the output tray or ask the booth operator to check the print queue."


class PrintState(StrEnum):
    QUEUED = "queued"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    SENT = "sent"
    FAILED = "failed"
    UNKNOWN = "unknown"


class PrintJob(Base):
    __tablename__ = "print_jobs"
    __table_args__ = (
        CheckConstraint("(original_id IS NULL) <> (filmstrip_id IS NULL)", name="print_job_one_asset"),
        CheckConstraint("state IN ('queued', 'submitting', 'submitted', 'sent', 'failed', 'unknown')",
                        name="print_job_state"),
        Index("ix_print_jobs_state_updated_at", "state", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    original_id: Mapped[UUID | None] = mapped_column(ForeignKey("original_photos.id"), unique=True)
    filmstrip_id: Mapped[UUID | None] = mapped_column(ForeignKey("filmstrips.id"), unique=True)
    printer: Mapped[str]
    state: Mapped[str] = mapped_column(String(16))
    detail: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PrintRequest(BaseModel):
    asset_id: UUID
    kind: ResultKind


class PrintView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    state: PrintState
    detail: str


@dataclass(frozen=True)
class SpoolResult:
    state: PrintState
    detail: str


def printer_configured(settings: Settings) -> bool:
    return bool(settings.printer_name) and sys.platform == "win32"


def result_job(db, asset_id: UUID, kind: ResultKind) -> PrintJob | None:
    column = PrintJob.original_id if kind == "original" else PrintJob.filmstrip_id
    return db.scalar(select(PrintJob).where(column == asset_id))


@router.get("", response_model=PrintView | None)
def print_status(asset_id: UUID, kind: ResultKind, request: Request,
                 booth_customer: str | None = Cookie(default=None)):
    with request.app.state.db() as db:
        session = require_session(db, booth_customer)
        require_result(db, session.id, asset_id, kind)
        return result_job(db, asset_id, kind)


@router.post("", response_model=PrintView, status_code=202)
def request_print(body: PrintRequest, request: Request, response: Response,
                  booth_customer: str | None = Cookie(default=None)):
    settings = request.app.state.settings
    with request.app.state.db.begin() as db:
        session = require_session(db, booth_customer, lock=True)
        asset = require_result(db, session.id, body.asset_id, body.kind)
        job = result_job(db, asset, body.kind)
        if job is not None and job.state != PrintState.FAILED:
            response.status_code = 200
            return job
        if not printer_configured(settings):
            raise HTTPException(503, "Printing is unavailable on this booth.")
        stored_file(request, "originals" if body.kind == "original" else "processed", asset)
        now = datetime.now(UTC)
        if job is None:
            job = PrintJob(
                id=uuid4(), created_at=now, original_id=asset if body.kind == "original" else None,
                filmstrip_id=asset if body.kind == "filmstrip" else None,
            )
            db.add(job)
        job.printer = settings.printer_name
        job.state, job.detail, job.updated_at = PrintState.QUEUED, QUEUED_DETAIL, now
        return job


def windows_job(job: PrintJob, image: Path | None) -> SpoolResult:
    executable = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    command = [
        str(executable), "-NoProfile", "-NonInteractive", "-File", str(ROOT / "scripts/print-jpeg.ps1"),
        "-Action", "Submit" if image is not None else "Status",
        "-Printer", job.printer, "-Document", f"Photo Booth {job.id}",
    ]
    if image is not None:
        command.extend(["-Layout", "Filmstrip" if job.filmstrip_id else "Photo", "-ImagePath", str(image)])
    try:
        result = subprocess.run(command, capture_output=True, timeout=SUBMISSION_TIMEOUT if image else 8,
                                creationflags=subprocess.CREATE_NO_WINDOW, check=True)
        report = json.loads(result.stdout)
        state = PrintState(report["state"])
        detail = report["detail"]
        if not isinstance(detail, str) or state not in {
            PrintState.SUBMITTED, PrintState.SENT, PrintState.FAILED, PrintState.UNKNOWN,
        }:
            raise ValueError("Invalid spooler response")
        return SpoolResult(state, detail)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as exc:
        log.warning("Print job %s Windows call failed (%s).", job.id, type(exc).__name__)
        if image is not None:
            return SpoolResult(PrintState.UNKNOWN, UNCERTAIN_DETAIL)
        return SpoolResult(PrintState.SUBMITTED, "Waiting for Windows to report the print status.")


def next_job(sessions) -> PrintJob | None:
    now = datetime.now(UTC)
    with sessions.begin() as db:
        job = db.scalar(
            select(PrintJob).where(
                (PrintJob.state.in_((PrintState.QUEUED, PrintState.SUBMITTED))) |
                ((PrintJob.state == PrintState.SUBMITTING) & (PrintJob.updated_at < now - RECOVERY_DELAY))
            ).order_by(PrintJob.updated_at).limit(1).with_for_update(skip_locked=True)
        )
        if job is not None and job.state == PrintState.QUEUED:
            job.state, job.detail = PrintState.SUBMITTING, "Sending to the printer…"
            job.updated_at = now
        elif job is not None and job.state == PrintState.SUBMITTING:
            # The prior worker may have printed before it could record the Windows result.
            job.state, job.detail, job.updated_at = PrintState.UNKNOWN, UNCERTAIN_DETAIL, now
        return job


def process_print_queue(settings: Settings, sessions) -> None:
    job = next_job(sessions)
    if job is None or job.state == PrintState.UNKNOWN:
        return
    if job.state == PrintState.SUBMITTED:
        result = windows_job(job, None)
    elif job.printer != settings.printer_name:
        result = SpoolResult(PrintState.FAILED, "The configured printer changed. Check it and try again.")
    else:
        area, asset = ("originals", job.original_id) if job.original_id else ("processed", job.filmstrip_id)
        try:
            image = asset_path(settings.data_root, area, asset)
            if not image.is_file():
                raise FileNotFoundError
        except (OSError, ValueError):
            result = SpoolResult(PrintState.FAILED, "The saved image is unavailable for printing.")
        else:
            result = windows_job(job, image)
    with sessions.begin() as db:
        current = db.get(PrintJob, job.id, with_for_update=True)
        if current is not None and current.state == job.state and current.updated_at == job.updated_at:
            current.state, current.detail, current.updated_at = result.state, result.detail, datetime.now(UTC)


@asynccontextmanager
async def print_worker(settings: Settings, sessions):
    if not printer_configured(settings):
        yield
        return
    stopped = asyncio.Event()

    async def run():
        while not stopped.is_set():
            try:
                await asyncio.to_thread(process_print_queue, settings, sessions)
            except SQLAlchemyError as exc:
                log.warning("Could not update the local print queue (%s).", type(exc).__name__)
            try:
                await asyncio.wait_for(stopped.wait(), timeout=2)
            except TimeoutError:
                pass

    task = asyncio.create_task(run())
    try:
        yield
    finally:
        stopped.set()
        await task
