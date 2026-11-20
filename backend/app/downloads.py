"""Issue phone links locally and serve only the linked file on the LAN listener."""

import asyncio
import logging
import re
import socket
from base64 import b64encode
from contextlib import asynccontextmanager, nullcontext
from datetime import UTC, datetime, timedelta
from io import BytesIO
from ipaddress import IPv4Address
from uuid import UUID

import qrcode
import uvicorn
from fastapi import APIRouter, Cookie, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from qrcode.image.pil import PilImage
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.ai_photos import AIJob, JobState
from app.config import Settings
from app.creative import creative_owner_query
from app.db import Base
from app.i18n import legacy_messages, phone_locale, translate
from app.photos import Filmstrip, OriginalPhoto, require_session, stored_file
from app.results import RESULT_AREAS, PhotoResultKind, require_owned_result
from app.security import issue_token, token_digest
from app.sessions import BoothSession, State

log = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api/sessions/current/photos/phone-links", tags=["downloads"])
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")
DELIVERY_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}
FILENAMES: dict[PhotoResultKind, str] = {
    "original": "photo-booth.jpg",
    "effect": "photo-booth-effect.jpg",
    "creative": "creative-studio.jpg",
}


class DownloadLink(Base):
    __tablename__ = "download_links"
    __table_args__ = (
        CheckConstraint("num_nonnulls(original_id, filmstrip_id, effect_id, creative_id) = 1",
                        name="download_link_one_asset"),
    )

    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    original_id: Mapped[UUID | None] = mapped_column(ForeignKey("original_photos.id", ondelete="CASCADE"))
    filmstrip_id: Mapped[UUID | None] = mapped_column(ForeignKey("filmstrips.id", ondelete="CASCADE"))
    effect_id: Mapped[UUID | None] = mapped_column(ForeignKey("ai_jobs.id", ondelete="CASCADE"))
    creative_id: Mapped[UUID | None] = mapped_column(ForeignKey("creative_results.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class LinkRequest(BaseModel):
    asset_id: UUID
    kind: PhotoResultKind


class PhoneLink(BaseModel):
    url: str
    qr_image: str
    expires_at: datetime


def delivery_error(request: Request, status: int, key: str) -> PlainTextResponse:
    locale = phone_locale(request.headers.get("Accept-Language", ""))
    return PlainTextResponse(translate(key, locale), status_code=status,
                             headers={"Content-Language": locale, "Vary": "Accept-Language"})


def qr_image(url: str) -> str:
    with BytesIO() as output:
        qrcode.make(url, image_factory=PilImage, box_size=8).save(output, format="PNG")
        return "data:image/png;base64," + b64encode(output.getvalue()).decode("ascii")


@router.post("", status_code=201, response_model=PhoneLink)
def create_phone_link(body: LinkRequest, request: Request, booth_customer: str | None = Cookie(default=None)):
    with request.app.state.db.begin() as db:
        session = require_session(db, booth_customer, lock=True)
        asset = require_owned_result(db, session.id, body.asset_id, body.kind)
        stored_file(request, RESULT_AREAS[body.kind], asset)
        base = request.app.state.download_base
        if base is None:
            raise HTTPException(503, "Phone downloads are unavailable on this booth.")
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=request.app.state.settings.download_ttl_minutes)
        token = issue_token()
        url = f"{base}/d/{token}"
        db.execute(delete(DownloadLink).where(DownloadLink.expires_at <= now))
        db.add(DownloadLink(digest=token_digest(token), expires_at=expires_at,
                            original_id=asset if body.kind == "original" else None,
                            filmstrip_id=asset if body.kind == "filmstrip" else None,
                            effect_id=asset if body.kind == "effect" else None,
                            creative_id=asset if body.kind == "creative" else None))
        return PhoneLink(url=url, qr_image=qr_image(url), expires_at=expires_at)


def create_delivery_app(settings: Settings, sessions) -> FastAPI:
    interface = settings.download_bind
    if interface is None:
        raise ValueError("A download listener needs a LAN interface")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)
    app.state.settings = settings
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[str(interface.ip)])

    @app.middleware("http")
    async def local_network(request: Request, call_next):
        try:
            allowed = request.client is not None and IPv4Address(request.client.host) in interface.network
        except ValueError:
            allowed = False
        response = await call_next(request) if allowed else delivery_error(request, 404, "messages.phoneMissing")
        response.headers.update(DELIVERY_HEADERS)
        return response

    @app.exception_handler(SQLAlchemyError)
    async def unavailable(request: Request, exc: SQLAlchemyError):
        log.warning("Phone download database operation failed (%s).", type(exc).__name__)
        return delivery_error(request, 503, "messages.phoneBusy")

    @app.exception_handler(StarletteHTTPException)
    async def localized_download_error(request: Request, exc: StarletteHTTPException):
        fallback = "messages.phoneExpired" if request.url.path.startswith("/d/") else "messages.phoneMissing"
        key = legacy_messages(exc.detail, fallback)[0].key
        response = delivery_error(request, exc.status_code, key)
        response.headers.update(exc.headers or {})
        return response

    @app.api_route("/d/{token}", methods=["GET", "HEAD"])
    def get_download(token: str, request: Request):
        unavailable_link = "This download link is invalid or has expired."
        if not TOKEN_PATTERN.fullmatch(token):
            raise HTTPException(404, unavailable_link)
        with sessions() as db:
            link = db.get(DownloadLink, token_digest(token))
            if link is None or link.expires_at <= datetime.now(UTC):
                raise HTTPException(404, unavailable_link)
            strip = None
            if link.creative_id is not None:
                kind, asset_id = "creative", link.creative_id
                owner_id = db.scalar(creative_owner_query(asset_id))
            elif link.effect_id is not None:
                kind, asset_id = "effect", link.effect_id
                owner_id = db.scalar(select(OriginalPhoto.session_id).join(
                    AIJob, AIJob.original_id == OriginalPhoto.id,
                ).where(AIJob.id == asset_id, AIJob.state == JobState.COMPLETED))
            elif link.original_id is not None:
                kind, asset_id = "original", link.original_id
                owner_id = db.scalar(select(OriginalPhoto.session_id).where(OriginalPhoto.id == asset_id))
            else:
                kind, asset_id = "filmstrip", link.filmstrip_id
                strip = db.get(Filmstrip, asset_id)
                owner_id = strip.session_id if strip is not None else None
            owner = db.get(BoothSession, owner_id) if owner_id is not None else None
            if owner is None or owner.state == State.CANCELED:
                raise HTTPException(404, unavailable_link)
            path = stored_file(request, RESULT_AREAS[kind], asset_id)
            filename = strip.filename(owner) if strip is not None else FILENAMES[kind]
        return FileResponse(path, media_type="image/jpeg", filename=filename, headers=DELIVERY_HEADERS)

    return app


class DownloadServer(uvicorn.Server):
    def capture_signals(self):
        # The booth's main listener owns process signals and shuts this listener down.
        return nullcontext()


@asynccontextmanager
async def delivery_listener(settings: Settings, sessions):
    if settings.download_bind is None:
        yield None
        return
    host, port = str(settings.download_bind.ip), settings.download_port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind((host, port))
            listener.listen()
            listener.setblocking(False)
        except OSError as exc:
            log.warning("Could not bind the phone download listener to %s:%s (%s).", host, port, exc.strerror)
            yield None
            return
        server = DownloadServer(uvicorn.Config(
            create_delivery_app(settings, sessions), host=host, port=port, access_log=False,
            log_config=None, lifespan="off", proxy_headers=False, ws="none", timeout_graceful_shutdown=3,
        ))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            while not server.started and not task.done():
                await asyncio.sleep(.01)
            if server.started:
                log.info("Phone downloads available at http://%s:%s.", host, port)
            yield f"http://{host}:{port}" if server.started else None
        finally:
            server.should_exit = True
            await task
