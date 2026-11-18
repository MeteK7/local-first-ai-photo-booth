from datetime import UTC, datetime, timedelta
from threading import Lock
from time import monotonic
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, String, select
from sqlalchemy.orm import Mapped, mapped_column

from app.camera import CameraDetails
from app.db import Base
from app.security import DUMMY_HASH, check_password, issue_token, token_digest
from app.sessions import BoothSession, SessionView

router = APIRouter(prefix="/api/admin", tags=["admin"])
COOKIE = "booth_admin"
LIFETIME = timedelta(hours=4)


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))


class AdminLogin(Base):
    __tablename__ = "admin_logins"

    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("admin_users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LoginThrottle:
    """One bounded attempt window for the local admin login."""

    def __init__(self) -> None:
        self.lock = Lock()
        self.deadline = 0.0
        self.count = 0

    def claim(self) -> None:
        with self.lock:
            now = monotonic()
            if now >= self.deadline:
                self.count = 0
                self.deadline = now + 60
            if self.count >= 8:
                raise HTTPException(429, "Try again in a minute.")
            self.count += 1

    def clear(self) -> None:
        with self.lock:
            self.count = 0


def get_login(db, token: str | None) -> AdminLogin | None:
    if not token:
        return None
    login = db.get(AdminLogin, token_digest(token))
    if login and login.revoked_at is None and login.expires_at > datetime.now(UTC):
        return login
    return None


def require_admin(db, token: str | None) -> AdminUser:
    login = get_login(db, token)
    if login is None:
        raise HTTPException(401, "Sign in to continue.")
    user = db.get(AdminUser, login.user_id)
    if user is None:
        raise HTTPException(401, "Sign in to continue.")
    return user


@router.post("/login")
def sign_in(body: Credentials, request: Request, response: Response,
            booth_admin: str | None = Cookie(default=None)):
    throttle = request.app.state.login_throttle
    throttle.claim()
    now = datetime.now(UTC)
    with request.app.state.db.begin() as db:
        user = db.scalar(select(AdminUser).where(AdminUser.username == body.username.strip().lower()))
        if not check_password(user.password_hash if user else DUMMY_HASH, body.password) or user is None:
            raise HTTPException(401, "The username or password is incorrect.")
        previous = get_login(db, booth_admin)
        if previous:
            previous.revoked_at = now
        token = issue_token()
        db.add(AdminLogin(digest=token_digest(token), user_id=user.id, expires_at=now + LIFETIME))
        response.set_cookie(
            COOKIE, token, httponly=True, samesite="strict", path="/api/admin",
            max_age=int(LIFETIME.total_seconds()),
        )
    throttle.clear()
    return {"username": user.username}


@router.post("/logout", status_code=204)
def sign_out(request: Request, response: Response, booth_admin: str | None = Cookie(default=None)):
    with request.app.state.db.begin() as db:
        login = get_login(db, booth_admin)
        if login:
            login.revoked_at = datetime.now(UTC)
    response.delete_cookie(COOKIE, path="/api/admin", httponly=True, samesite="strict")


@router.get("/overview")
def overview(request: Request, booth_admin: str | None = Cookie(default=None)):
    with request.app.state.db() as db:
        user = require_admin(db, booth_admin)
        return {
            "username": user.username,
            "database": "ready",
            "camera": request.app.state.camera.status().state,
            "storage": str(request.app.state.settings.data_root),
            "sessions": [
                SessionView.model_validate(row)
                for row in db.scalars(select(BoothSession).order_by(BoothSession.started_at.desc()).limit(30))
            ],
        }


@router.get("/camera", response_model=CameraDetails)
def camera_details(request: Request, booth_admin: str | None = Cookie(default=None)):
    with request.app.state.db() as db:
        require_admin(db, booth_admin)
    return request.app.state.camera.details()
