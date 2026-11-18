"""Capture, preserve and serve photos for a single active booth session."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, ConfigDict, UUID4
from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.filmstrip import FRAME_COUNT, HEIGHT, WIDTH, render_filmstrip
from app.media import asset_path, jpeg_dimensions, save_jpeg, save_original
from app.sessions import Experience, active_session

router = APIRouter(prefix="/api/sessions/current/photos", tags=["photos"])
ResultKind = Literal["original", "filmstrip"]


class OriginalPhoto(Base):
    __tablename__ = "original_photos"
    __table_args__ = (
        UniqueConstraint("session_id", "request_id", name="original_photo_capture_request"),
        Index("ix_original_photos_session_captured", "session_id", "captured_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("booth_sessions.id"))
    request_id: Mapped[UUID]
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    byte_size: Mapped[int]
    width: Mapped[int]
    height: Mapped[int]


class Filmstrip(Base):
    __tablename__ = "filmstrips"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("booth_sessions.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    byte_size: Mapped[int]
    width: Mapped[int]
    height: Mapped[int]


class CaptureRequest(BaseModel):
    request_id: UUID4


class PhotoView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    captured_at: datetime
    byte_size: int
    width: int
    height: int


class FilmstripView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    byte_size: int
    width: int
    height: int


class FilmstripProgress(BaseModel):
    captured: int
    required: int = FRAME_COUNT
    result: FilmstripView | None = None


def require_session(db, token: str | None, *, lock: bool = False):
    session = active_session(db, token, datetime.now(UTC), lock=lock)
    if session is None:
        raise HTTPException(404, "There is no active session.")
    return session


def filmstrip_session(db, token: str | None, *, lock: bool = False):
    session = require_session(db, token, lock=lock)
    if session.experience != Experience.FILMSTRIP:
        raise HTTPException(404, "There is no active filmstrip session.")
    return session


def strip_originals(db, session_id: UUID) -> list[OriginalPhoto]:
    return list(db.scalars(
        select(OriginalPhoto).where(OriginalPhoto.session_id == session_id)
        .order_by(OriginalPhoto.captured_at, OriginalPhoto.id).limit(FRAME_COUNT)
    ))


def saved_filmstrip(db, session_id: UUID) -> Filmstrip | None:
    return db.scalar(select(Filmstrip).where(Filmstrip.session_id == session_id))


@router.get("/live-view")
def live_view(request: Request, booth_customer: str | None = Cookie(default=None)):
    with request.app.state.db() as db:
        owner = require_session(db, booth_customer).id
    return Response(request.app.state.camera.frame(owner), media_type="image/jpeg")


@router.get("/latest", response_model=PhotoView | None)
def latest(request: Request, booth_customer: str | None = Cookie(default=None)):
    with request.app.state.db() as db:
        session = require_session(db, booth_customer)
        return db.scalar(
            select(OriginalPhoto).where(OriginalPhoto.session_id == session.id)
            .order_by(OriginalPhoto.captured_at.desc(), OriginalPhoto.id.desc()).limit(1)
        )


@router.get("/filmstrip", response_model=FilmstripProgress)
def filmstrip_progress(request: Request, booth_customer: str | None = Cookie(default=None)):
    with request.app.state.db() as db:
        session = filmstrip_session(db, booth_customer)
        return FilmstripProgress(
            captured=len(strip_originals(db, session.id)), result=saved_filmstrip(db, session.id),
        )


@router.post("/filmstrip", response_model=FilmstripView)
def compose_filmstrip(request: Request, booth_customer: str | None = Cookie(default=None)):
    root = request.app.state.settings.data_root
    with request.app.state.db.begin() as db:
        session = filmstrip_session(db, booth_customer, lock=True)
        existing = saved_filmstrip(db, session.id)
        try:
            if existing is not None and asset_path(root, "processed", existing.id).is_file():
                return existing
            originals = strip_originals(db, session.id)
            if len(originals) != FRAME_COUNT:
                raise HTTPException(409, "Take all three photos before creating the filmstrip.")
            jpeg = render_filmstrip([asset_path(root, "originals", photo.id) for photo in originals])
            result = existing or Filmstrip(
                id=uuid4(), session_id=session.id, width=WIDTH, height=HEIGHT,
                created_at=datetime.now(UTC),
            )
            result.byte_size = len(jpeg)
            db.add(result)
            db.flush()
            save_jpeg(root, "processed", result.id, jpeg)
            return result
        except (OSError, ValueError, Image.DecompressionBombError):
            raise HTTPException(503, "Could not create the filmstrip. Your originals are saved. Try again.") from None


@router.post("", status_code=201, response_model=PhotoView)
def capture(body: CaptureRequest, request: Request, response: Response,
            booth_customer: str | None = Cookie(default=None)):
    # Prevent concurrently finishing this session or repeating the same shutter request.
    with request.app.state.db.begin() as db:
        session = require_session(db, booth_customer, lock=True)
        existing = db.scalar(select(OriginalPhoto).where(
            OriginalPhoto.session_id == session.id, OriginalPhoto.request_id == body.request_id,
        ))
        if existing is not None:
            response.status_code = 200
            return existing
        if session.experience == Experience.FILMSTRIP and len(strip_originals(db, session.id)) == FRAME_COUNT:
            raise HTTPException(409, "This filmstrip already has all three photos.")
        jpeg = request.app.state.camera.capture(session.id)
        try:
            width, height = jpeg_dimensions(jpeg)
        except ValueError:
            raise HTTPException(502, "The camera returned an invalid JPEG.") from None
        photo = OriginalPhoto(id=uuid4(), session_id=session.id, request_id=body.request_id,
                              captured_at=datetime.now(UTC), byte_size=len(jpeg), width=width, height=height)
        db.add(photo)
        db.flush()
        try:
            save_original(request.app.state.settings.data_root, photo.id, jpeg)
        except (OSError, ValueError):
            raise HTTPException(503, "Could not save the photo. Ask the booth operator to check storage.") from None
        return photo


def stored_file(request: Request, area: str, asset_id: UUID) -> Path:
    try:
        path = asset_path(request.app.state.settings.data_root, area, asset_id)
        if not path.is_file():
            raise HTTPException(404, "Photo file not found.")
    except (OSError, ValueError):
        raise HTTPException(404, "Photo file not found.") from None
    return path


def require_result(db, session_id: UUID, asset_id: UUID, kind: ResultKind) -> UUID:
    model = OriginalPhoto if kind == "original" else Filmstrip
    asset = db.scalar(select(model.id).where(model.id == asset_id, model.session_id == session_id))
    if asset is None:
        raise HTTPException(404, "Photo not found.")
    return asset


def owned_photo(request: Request, token: str | None, photo_id: UUID) -> Path:
    with request.app.state.db() as db:
        session = require_session(db, token)
        photo = db.scalar(select(OriginalPhoto.id).where(
            OriginalPhoto.id == photo_id, OriginalPhoto.session_id == session.id,
        ))
    if photo is None:
        raise HTTPException(404, "Photo not found.")
    return stored_file(request, "originals", photo_id)


def owned_filmstrip(request: Request, token: str | None, strip_id: UUID) -> Path:
    with request.app.state.db() as db:
        session = filmstrip_session(db, token)
        result = saved_filmstrip(db, session.id)
    if result is None or result.id != strip_id:
        raise HTTPException(404, "Filmstrip not found.")
    return stored_file(request, "processed", strip_id)


@router.get("/filmstrip/{strip_id}/preview")
def preview_filmstrip(strip_id: UUID, request: Request, booth_customer: str | None = Cookie(default=None)):
    return FileResponse(owned_filmstrip(request, booth_customer, strip_id), media_type="image/jpeg")


@router.get("/filmstrip/{strip_id}/download")
def download_filmstrip(strip_id: UUID, request: Request, booth_customer: str | None = Cookie(default=None)):
    return FileResponse(owned_filmstrip(request, booth_customer, strip_id), media_type="image/jpeg",
                        filename="classic-filmstrip.jpg")


@router.get("/{photo_id}/preview")
def preview(photo_id: UUID, request: Request, booth_customer: str | None = Cookie(default=None)):
    return FileResponse(owned_photo(request, booth_customer, photo_id), media_type="image/jpeg")


@router.get("/{photo_id}/download")
def download(photo_id: UUID, request: Request, booth_customer: str | None = Cookie(default=None)):
    return FileResponse(owned_photo(request, booth_customer, photo_id), media_type="image/jpeg",
                        filename="photo-booth.jpg")
