import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles

from app.admin import LoginThrottle
from app.admin import router as admin_router
from app.ai_photos import ai_worker, router as ai_router
from app.camera import Camera, CameraFailure, CameraStatus
from app.config import Settings
from app.db import make_engine
from app.downloads import delivery_listener, router as downloads_router
from app.image_provider import ImageProvider, select_provider
from app.media import MEDIA_AREAS, prepare_storage
from app.photos import router as photos_router
from app.printing import print_worker, router as printing_router
from app.sessions import router as sessions_router

log = logging.getLogger("uvicorn.error")
LOCAL_ORIGINS = {
    f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (4200, 8000)
}
SCHEMA_REVISION = "20261118_07"


def create_app(settings: Settings | None = None, *, image_provider: ImageProvider | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings)
    camera = Camera(settings.camera_enabled)
    provider = image_provider if image_provider is not None else select_provider(settings.ai_mode)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            prepare_storage(settings.data_root)
        except OSError:
            log.error("Cannot prepare the configured photo storage.")
        log.info("Photo booth started.")
        try:
            async with delivery_listener(settings, app.state.db) as base:
                app.state.download_base = base
                async with print_worker(settings, app.state.db), ai_worker(settings, app.state.db, provider):
                    yield
        finally:
            camera.close()
            engine.dispose()
            log.info("Photo booth stopped.")

    app = FastAPI(title="Local Photo Booth", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db = sessionmaker(engine, expire_on_commit=False)
    app.state.settings = settings
    app.state.login_throttle = LoginThrottle()
    app.state.camera = camera
    app.state.download_base = None
    app.state.image_provider = provider
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if (request.headers.get("x-booth-request") != "1"
                    or origin is not None and origin not in LOCAL_ORIGINS):
                return JSONResponse({"detail": "Request origin is not allowed."}, status_code=403)
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_request: Request, exc: SQLAlchemyError):
        log.warning("Database operation failed (%s).", type(exc).__name__)
        return JSONResponse({"detail": "The local database is unavailable."}, status_code=503)

    @app.exception_handler(RequestValidationError)
    async def bad_request(_request: Request, _exc: RequestValidationError):
        return JSONResponse({"detail": "Check the supplied values."}, status_code=422)

    @app.exception_handler(CameraFailure)
    async def camera_error(_request: Request, exc: CameraFailure):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.get("/api/health/live")
    def live():
        return {"status": "live"}

    @app.get("/api/health/ready")
    def ready():
        try:
            with engine.connect() as conn:
                database_ready = conn.scalar(text(
                    "SELECT version_num FROM alembic_version"
                )) == SCHEMA_REVISION
        except SQLAlchemyError:
            database_ready = False
        storage_ready = all((settings.data_root / area).is_dir() for area in
                            MEDIA_AREAS)
        healthy = database_ready and storage_ready
        return JSONResponse({
            "status": "ready" if healthy else "unavailable",
            "database": "ready" if database_ready else "unavailable",
            "storage": "ready" if storage_ready else "unavailable",
        }, status_code=200 if healthy else 503)

    @app.get("/api/camera/status", response_model=CameraStatus, response_model_exclude_none=True)
    def camera_status():
        return camera.status()

    app.include_router(sessions_router)
    app.include_router(photos_router)
    app.include_router(downloads_router)
    app.include_router(printing_router)
    app.include_router(ai_router)
    app.include_router(admin_router)
    index = settings.frontend_dir / "index.html"
    if index.is_file():
        def spa():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})

        for route in ("/", "/session", "/admin"):
            app.add_api_route(route, spa, methods=["GET"])
        app.mount("/", StaticFiles(directory=settings.frontend_dir), name="frontend")
    return app
