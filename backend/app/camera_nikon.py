"""Nikon D5600 operations over the Windows WPD/PTP transport."""

import logging
from contextlib import contextmanager, suppress
from struct import error as StructError
from struct import unpack_from
from time import monotonic, sleep

from app.camera import CameraDetails, CameraFailure, CameraStatus
from app.camera_wpd import COMError, PortableDevice, PtpResponseError, WpdCommandError, WpdError, find_d5600

GET_INFO = 0x1001
GET_STORAGE_IDS = 0x1004
GET_OBJECT_HANDLES = 0x1007
GET_OBJECT_INFO = 0x1008
GET_PROPERTY = 0x1015
GET_PARTIAL_OBJECT = 0x101B
BATTERY = 0x5001
FOCUS_MODE = 0x500A
MANUAL_FOCUS = 1
LIVE_VIEW_STATUS = 0xD1A2
LIVE_VIEW_INHIBIT = 0xD1A4
DRIVE_AUTOFOCUS = 0x90C1
DEVICE_READY = 0x90C8
START_LIVE_VIEW, STOP_LIVE_VIEW, GET_LIVE_FRAME = 0x9201, 0x9202, 0x9203
CAPTURE_TO_MEDIA = 0x9207
SHUTTER_WITH_AUTOFOCUS, SHUTTER_WITHOUT_AUTOFOCUS = 0xFFFFFFFE, 0xFFFFFFFF
SD_CARD = 0
JPEG_FORMAT = 0x3801
DEVICE_BUSY, NOT_IN_LIVE_VIEW = 0x2019, 0xA00B
RETRYABLE_TRANSFER_ERRORS = {0x8007001F, 0x800704C7}
JPEG_LIMIT = 32 * 1024 * 1024
TRANSFER_CHUNK = 512 * 1024
LIVE_VIEW_COMMANDS = {START_LIVE_VIEW, STOP_LIVE_VIEW, GET_LIVE_FRAME}
CAPTURE_COMMANDS = {
    CAPTURE_TO_MEDIA, GET_STORAGE_IDS, GET_OBJECT_HANDLES, GET_OBJECT_INFO, GET_PARTIAL_OBJECT,
}
JPEG_START, JPEG_END = b"\xff\xd8\xff", b"\xff\xd9"
log = logging.getLogger(__name__)

# D5600 reports physical live-view interlocks in a 32-bit field.
BATTERY_EXHAUSTED = 1 << 8
LENS_RETRACTED = 1 << 24
UNSUPPORTED_EXPOSURE_MODE = 1 << 31


def supported_operations(info: bytes) -> frozenset[int]:
    if len(info) < 15:
        raise WpdError("The camera sent incomplete device information.")
    # PTP DeviceInfo starts with version fields, an extension string, and functional mode.
    count_offset = 11 + 2 * info[8]
    try:
        count = unpack_from("<I", info, count_offset)[0]
        available = (len(info) - count_offset - 4) // 2
        if count > available:
            raise WpdError("The camera sent an invalid operation list.")
        return frozenset(unpack_from(f"<{count}H", info, count_offset + 4))
    except StructError:
        raise WpdError("The camera sent incomplete device information.") from None


class NikonD5600:
    def __init__(self):
        self.device: PortableDevice | None = None
        self.device_id = None
        self.operations: frozenset[int] = frozenset()
        self.preview_owner = None
        self.preview_until = 0.0

    @contextmanager
    def _connected(self):
        try:
            device_id = find_d5600()
            if device_id is None:
                self.close()
                raise CameraFailure("Connect and turn on the Nikon D5600.")
            if self.device_id != device_id:
                self.close()
                self.device = PortableDevice(device_id)
                self.operations = supported_operations(self.device.read(GET_INFO, limit=65536))
                self.device_id = device_id
            yield self.device
        except PtpResponseError as error:
            messages = {
                DEVICE_BUSY: "The camera is busy. Try again in a moment.",
                0x200F: "The camera refused the operation. Check its battery and shooting mode.",
                0xA002: "The camera could not focus. Check the lighting and try again.",
                0xA004: "The camera is unable to shoot in its current mode. Check its display.",
            }
            log.warning("%s", error)
            raise CameraFailure(messages.get(error.response, "The camera rejected the requested operation."),
                                409 if error.response == DEVICE_BUSY else 503) from None
        except (COMError, WpdError) as error:
            log.warning("D5600 USB transport error: %s",
                        str(error) if isinstance(error, WpdError) else hex(error.hresult & 0xFFFFFFFF))
            self.close()
            raise CameraFailure("Camera communication failed. Check the USB connection.") from None

    @staticmethod
    def _setting(device, code: int, *, signed: bool = False) -> int | None:
        try:
            data = device.read(GET_PROPERTY, code, limit=4096)
        except PtpResponseError as error:
            if error.response in {0x2005, 0x200A}:
                return None
            raise
        return int.from_bytes(data, "little", signed=signed) if len(data) in {1, 2, 4} else None

    def _status(self, device) -> CameraStatus:
        battery = self._setting(device, BATTERY)
        live_view = LIVE_VIEW_COMMANDS <= self.operations
        capture = CAPTURE_COMMANDS <= self.operations
        inhibits = self._setting(device, LIVE_VIEW_INHIBIT) or 0
        instructions = []
        if (battery is not None and battery <= 5) or inhibits & BATTERY_EXHAUSTED:
            instructions.append("Charge the camera battery.")
        if inhibits & LENS_RETRACTED:
            instructions.append("Extend the camera lens.")
        if inhibits & UNSUPPORTED_EXPOSURE_MODE:
            instructions.append("Turn the camera mode dial to P, A, S, or M.")
        if not (live_view and capture):
            instructions.append("This camera configuration cannot preview and capture photos.")
        return CameraStatus(
            state="blocked" if instructions else "ready",
            model="Nikon D5600", battery_percent=battery, live_view=live_view,
            capture=capture, detail=" ".join(instructions) or None,
        )

    def status(self) -> CameraStatus:
        with self._connected() as device:
            status = self._status(device)
            if status.state == "ready":
                try:
                    device.execute(DEVICE_READY)
                except PtpResponseError as error:
                    if error.response != DEVICE_BUSY:
                        raise
                    status.state = "busy"
                    status.detail = "The camera is busy. Wait for it to finish."
            return status

    def details(self) -> CameraDetails:
        with self._connected() as device:
            aperture = self._setting(device, 0x5007)
            shutter = self._setting(device, 0x500D)
            compensation = self._setting(device, 0x5010, signed=True)
            focal_length = self._setting(device, 0x5008)
            return CameraDetails(
                status=self._status(device), iso=self._setting(device, 0x500F),
                aperture=aperture / 100 if aperture is not None else None,
                shutter_seconds=shutter / 10000 if shutter is not None else None,
                exposure_compensation_ev=compensation / 1000 if compensation is not None else None,
                focal_length_mm=focal_length / 100 if focal_length is not None else None,
                autofocus_available=DRIVE_AUTOFOCUS in self.operations,
            )

    def _ensure_ready(self, device, owner) -> None:
        if self.preview_owner is not None and self.preview_owner != owner:
            raise CameraFailure("Another booth session is using the camera.", 409)
        status = self._status(device)
        if status.state != "ready":
            raise CameraFailure(status.detail)

    def _start_preview(self, device, owner) -> None:
        if self.preview_owner == owner:
            return
        self._ensure_ready(device, owner)
        if not self._setting(device, LIVE_VIEW_STATUS):
            device.execute(START_LIVE_VIEW)
        self.preview_owner = owner
        self.preview_until = monotonic() + 4
        self._wait_until_ready(device)

    def frame(self, owner) -> bytes:
        with self._connected() as device:
            self._start_preview(device, owner)
            try:
                frame = device.read(GET_LIVE_FRAME, limit=4 * 1024 * 1024)
            except PtpResponseError as error:
                if error.response == NOT_IN_LIVE_VIEW:
                    self.preview_owner = None
                raise
            start, end = frame.find(JPEG_START), frame.rfind(JPEG_END)
            if start < 0 or end <= start:
                raise CameraFailure("The camera did not return a usable live frame.")
            self.preview_until = monotonic() + 4
            return frame[start:end + 2]

    def _stop_preview(self) -> None:
        if self.preview_owner is not None:
            try:
                self.device.execute(STOP_LIVE_VIEW)
            except PtpResponseError as error:
                if error.response != NOT_IN_LIVE_VIEW:
                    raise
            self.preview_owner = None

    def stop_idle_preview(self) -> None:
        if self.preview_owner is not None and monotonic() >= self.preview_until:
            try:
                self._stop_preview()
            except (COMError, WpdError):
                self.close()

    @staticmethod
    def _wait_until_ready(device) -> None:
        deadline = monotonic() + 3
        while True:
            try:
                device.execute(DEVICE_READY)
                return
            except PtpResponseError as error:
                if error.response != DEVICE_BUSY:
                    raise
                if monotonic() >= deadline:
                    raise CameraFailure("The camera stayed busy. Check its display and retry.", 504) from None
                sleep(.10)

    @staticmethod
    def _object_ids(data: bytes) -> frozenset[int]:
        if len(data) < 4 or len(data) % 4 or int.from_bytes(data[:4], "little") != (len(data) - 4) // 4:
            raise WpdError("The camera returned an invalid storage list.")
        return frozenset(unpack_from(f"<{(len(data) - 4) // 4}I", data, 4))

    def _card_objects(self, device, storage: int) -> frozenset[int]:
        return self._object_ids(device.read(GET_OBJECT_HANDLES, storage, 0, 0, limit=1024 * 1024))

    @staticmethod
    def _read_card_jpeg(device, handle: int) -> bytes:
        deadline = monotonic() + 8
        photo = bytearray()
        size = 0
        while monotonic() < deadline:
            try:
                if not photo:
                    # The card can announce an object while it is still finalizing the JPEG.
                    info = device.read(GET_OBJECT_INFO, handle, limit=65536)
                    if len(info) < 12:
                        raise WpdError("The camera returned incomplete JPEG metadata.")
                    size = unpack_from("<I", info, 8)[0]
                    if size == 0:
                        sleep(.20)
                        continue
                    if size > JPEG_LIMIT:
                        raise CameraFailure("The captured file exceeds the booth’s JPEG size limit.", 502)
                length = min(size - len(photo), TRANSFER_CHUNK)
                chunk = device.read(GET_PARTIAL_OBJECT, handle, len(photo), length, limit=length)
            except WpdCommandError as error:
                if error.result not in RETRYABLE_TRANSFER_ERRORS:
                    raise
                sleep(.20)
                continue
            if not chunk or (not photo and not chunk.startswith(JPEG_START)):
                photo.clear()
                sleep(.20)
                continue
            photo.extend(chunk)
            if len(photo) == size:
                if photo.endswith(JPEG_END):
                    return bytes(photo)
                photo.clear()
                sleep(.20)
        raise CameraFailure("The photo is on the SD card, but its USB transfer timed out.", 504)

    def capture(self, owner) -> bytes:
        with self._connected() as device:
            self._ensure_ready(device, owner)
            shutter_focus = SHUTTER_WITHOUT_AUTOFOCUS
            if self._setting(device, FOCUS_MODE) != MANUAL_FOCUS:
                if DRIVE_AUTOFOCUS in self.operations:
                    # Focus on the same live image the customer used to frame the shot.
                    self._start_preview(device, owner)
                    device.execute(DRIVE_AUTOFOCUS)
                    self._wait_until_ready(device)
                else:
                    shutter_focus = SHUTTER_WITH_AUTOFOCUS
            self._stop_preview()
            self._wait_until_ready(device)
            cards = self._object_ids(device.read(GET_STORAGE_IDS, limit=65536))
            if len(cards) != 1:
                raise CameraFailure("Insert a writable SD card in the D5600.", 422)
            storage = next(iter(cards))
            previous = self._card_objects(device, storage)
            device.execute(CAPTURE_TO_MEDIA, shutter_focus, SD_CARD)
            # A fresh Windows device handle can read the new card object after a still capture.
            device.close()
            self.device = device = PortableDevice(self.device_id)
            self._wait_until_ready(device)
            deadline = monotonic() + 9
            while monotonic() < deadline:
                candidates = []
                for handle in self._card_objects(device, storage) - previous:
                    info = device.read(GET_OBJECT_INFO, handle, limit=65536)
                    if len(info) >= 12 and unpack_from("<H", info, 4)[0] == JPEG_FORMAT:
                        candidates.append(handle)
                if len(candidates) > 1:
                    raise CameraFailure("The camera produced more than one JPEG. Select single-shot release.", 409)
                if candidates:
                    return self._read_card_jpeg(device, candidates[0])
                sleep(.25)
            raise CameraFailure("The camera did not deliver a photo. Wait for it to finish before retrying.", 504)

    def close(self) -> None:
        if self.device is not None:
            with suppress(COMError, WpdError):
                self._stop_preview()
            with suppress(COMError, WpdError):
                self.device.close()
        self.preview_owner = None
        self.device = self.device_id = None
        self.operations = frozenset()
