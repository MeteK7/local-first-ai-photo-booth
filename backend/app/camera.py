"""Application-facing camera operations and ownership of the local worker."""

import logging
import multiprocessing as mp
import sys
from threading import Lock
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

log = logging.getLogger("uvicorn.error")


class CameraStatus(BaseModel):
    state: Literal["unavailable", "ready", "busy", "blocked"]
    model: str | None = None
    battery_percent: int | None = None
    live_view: bool = False
    capture: bool = False
    detail: str | None = None


class CameraDetails(BaseModel):
    status: CameraStatus
    iso: int | None = None
    aperture: float | None = None
    shutter_seconds: float | None = None
    exposure_compensation_ev: float | None = None
    focal_length_mm: float | None = None
    autofocus_available: bool = False


class CameraFailure(Exception):
    def __init__(self, message: str, status: int = 503):
        super().__init__(message)
        self.status = status


def camera_worker(connection) -> None:
    adapter = None
    try:
        from app.camera_nikon import NikonD5600

        adapter = NikonD5600()
        while True:
            adapter.stop_idle_preview()
            if not connection.poll(1):
                continue
            operation, owner = connection.recv()
            if operation == "close":
                break
            try:
                match operation:
                    case "status":
                        value = adapter.status()
                    case "details":
                        value = adapter.details()
                    case "preview":
                        value = adapter.frame(owner)
                    case "capture":
                        value = adapter.capture(owner)
                connection.send((True, value))
            except CameraFailure as error:
                connection.send((False, (str(error), error.status)))
    except (EOFError, BrokenPipeError, KeyboardInterrupt):
        pass
    except Exception:
        log.exception("The local camera worker stopped.")
    finally:
        if adapter is not None:
            adapter.close()
        connection.close()


class Camera:
    def __init__(self, enabled: bool):
        self.enabled = enabled and sys.platform == "win32"
        self.lock = Lock()
        self.context = mp.get_context("spawn")
        self.connection = None
        self.process = None

    def status(self) -> CameraStatus:
        if not self.enabled:
            return CameraStatus(state="unavailable")
        try:
            return self._call("status", timeout=6)
        except CameraFailure as error:
            state = "busy" if error.status == 409 else "unavailable"
            return CameraStatus(state=state, detail=str(error))

    def details(self) -> CameraDetails:
        return self._call("details", timeout=8)

    def frame(self, session_id: UUID) -> bytes:
        return self._call("preview", session_id, timeout=6)

    def capture(self, session_id: UUID) -> bytes:
        return self._call("capture", session_id, timeout=22)

    def _call(self, operation: str, owner: UUID | None = None, *, timeout: int):
        if not self.enabled:
            raise CameraFailure("Camera unavailable.")
        if not self.lock.acquire(blocking=False):
            raise CameraFailure("The camera is busy. Try again in a moment.", 409)
        try:
            if not self.process or not self.process.is_alive():
                self._stop(graceful=False)
                local, remote = self.context.Pipe()
                process = self.context.Process(target=camera_worker, args=(remote,), daemon=True)
                try:
                    process.start()
                except OSError:
                    local.close()
                    raise CameraFailure("The camera worker could not start.") from None
                finally:
                    remote.close()
                self.connection, self.process = local, process
            try:
                self.connection.send((operation, owner))
                if not self.connection.poll(timeout):
                    self._stop(graceful=False)
                    raise CameraFailure("The camera timed out. Check the USB connection before trying again.", 504)
                success, value = self.connection.recv()
            except (EOFError, OSError):
                self._stop(graceful=False)
                raise CameraFailure("The camera connection was interrupted.") from None
            if not success:
                raise CameraFailure(*value)
            return value
        finally:
            self.lock.release()

    def _stop(self, *, graceful: bool) -> None:
        if not self.process:
            return
        if graceful and self.process.is_alive():
            try:
                self.connection.send(("close", None))
                self.process.join(2)
            except OSError:
                pass
        self.connection.close()
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(2)
        if not self.process.is_alive():
            self.process.close()
        self.connection, self.process = None, None

    def close(self) -> None:
        with self.lock:
            self._stop(graceful=True)
