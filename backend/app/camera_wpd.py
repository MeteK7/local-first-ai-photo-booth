"""Windows Portable Devices transport for the D5600 USB adapter."""

import os
from contextlib import suppress
from ctypes import (
    POINTER, byref, c_ubyte, c_ulong, c_ushort, c_void_p, c_wchar_p, cast, oledll,
    string_at, wstring_at,
)
from pathlib import Path

from comtypes import COMError, GUID
from comtypes.client import CreateObject, GetModule

SYSTEM32 = Path(os.environ["SystemRoot"]) / "System32"
API = GetModule(str(SYSTEM32 / "PortableDeviceApi.dll"))
TYPES = GetModule(str(SYSTEM32 / "PortableDeviceTypes.dll"))

VALUE_METHODS = {method.name: method for method in API.IPortableDeviceValues._methods_}
PropertyKey = VALUE_METHODS["SetStringValue"].argtypes[0]._type_
PropVariant = next(
    method.argtypes[0]._type_ for method in API.IPortableDevicePropVariantCollection._methods_
    if method.name == "Add"
)
PROPVARIANT_VALUE = PropVariant._fields_[-1][0]
COMMON = GUID("{F0422A9C-5DC8-4440-B5BD-5DF28835658A}")
MTP = GUID("{4D545058-1A2E-4106-A357-771E0819FC56}")
CLIENT_NAME = PropertyKey(GUID("{204D9F0C-2292-4080-9F42-40664E70F859}"), 2)
COMMAND_CATEGORY, COMMAND_ID, COMMAND_RESULT = (PropertyKey(COMMON, n) for n in (1001, 1002, 1003))
OPERATION, PARAMETERS, RESPONSE = (PropertyKey(MTP, n) for n in (1001, 1002, 1003))
CONTEXT, TOTAL_BYTES, REQUEST_BYTES, RECEIVED_BYTES, BUFFER, OPTIMAL = (
    PropertyKey(MTP, n) for n in (1006, 1007, 1008, 1009, 1012, 1013)
)

EXECUTE, EXECUTE_READ, READ, FINISH = 12, 13, 15, 17
OK = 0x2001
OLE_FREE = oledll.ole32.CoTaskMemFree
OLE_FREE.argtypes = (c_void_p,)
OLE_FREE.restype = None


class WpdError(Exception):
    pass


class WpdCommandError(WpdError):
    def __init__(self, result: int, command: int):
        self.result = result & 0xFFFFFFFF
        super().__init__(f"Windows camera command {command} failed (0x{self.result:08X}).")


class PtpResponseError(WpdError):
    def __init__(self, operation: int, response: int):
        self.response = response
        super().__init__(f"PTP operation 0x{operation:04X} returned 0x{response:04X}.")


def find_d5600() -> str | None:
    manager = CreateObject(API.PortableDeviceManager, interface=API.IPortableDeviceManager)
    manager.RefreshDeviceList()
    count = c_ulong()
    get_devices = manager._IPortableDeviceManager__com_GetDevices
    get_devices(None, byref(count))
    if count.value == 0:
        return None
    ids = (c_void_p * count.value)()
    matches = []
    try:
        get_devices(cast(ids, POINTER(c_wchar_p)), byref(count))
        for pointer in ids:
            if not pointer:
                continue
            device_id = wstring_at(pointer)
            if "vid_04b0" not in device_id.casefold():
                continue
            length = c_ulong()
            get_name = manager._IPortableDeviceManager__com_GetDeviceFriendlyName
            get_name(device_id, None, byref(length))
            name = (c_ushort * length.value)()
            get_name(device_id, name, byref(length))
            if wstring_at(name).strip().casefold() in {"d5600", "nikon d5600", "nikon dsc d5600"}:
                matches.append(device_id)
    finally:
        for pointer in ids:
            if pointer:
                OLE_FREE(pointer)
    if len(matches) > 1:
        raise WpdError("Connect one Nikon D5600 to this booth.")
    return matches[0] if matches else None


def values():
    return CreateObject(TYPES.PortableDeviceValues, interface=API.IPortableDeviceValues)


class PortableDevice:
    def __init__(self, device_id: str):
        info = values()
        info.SetStringValue(CLIENT_NAME, "Local Photo Booth")
        self.device = CreateObject(API.PortableDeviceFTM, interface=API.IPortableDevice)
        self.device.Open(device_id, info)

    def close(self) -> None:
        self.device.Close()

    def _parameters(self, operation: int, args: tuple[int, ...]):
        command = values()
        command.SetUnsignedIntegerValue(OPERATION, operation)
        params = CreateObject(
            TYPES.PortableDevicePropVariantCollection, interface=API.IPortableDevicePropVariantCollection
        )
        for arg in args:
            variant = PropVariant()
            variant.vt = 19  # VT_UI4
            getattr(variant, PROPVARIANT_VALUE).ulVal = arg
            params.Add(variant)
        command.SetIPortableDevicePropVariantCollectionValue(PARAMETERS, params)
        return command

    def _send(self, command_id: int, command):
        command.SetGuidValue(COMMAND_CATEGORY, MTP)
        command.SetUnsignedIntegerValue(COMMAND_ID, command_id)
        result = self.device.SendCommand(0, command)
        hresult = result.GetErrorValue(COMMAND_RESULT)
        if hresult < 0:
            raise WpdCommandError(hresult, command_id)
        return result

    @staticmethod
    def _check(operation: int, result) -> None:
        response = result.GetUnsignedIntegerValue(RESPONSE)
        if response != OK:
            raise PtpResponseError(operation, response)

    def execute(self, operation: int, *args: int) -> None:
        self._check(operation, self._send(EXECUTE, self._parameters(operation, args)))

    def read(self, operation: int, *args: int, limit: int = 32 * 1024 * 1024) -> bytes:
        opened = self._send(EXECUTE_READ, self._parameters(operation, args))
        try:
            context = c_wchar_p()
            opened._IPortableDeviceValues__com_GetStringValue(CONTEXT, byref(context))
        except COMError:
            self._check(operation, opened)
            raise WpdError("Windows returned no camera transfer context.") from None
        try:
            transfer = context.value
        finally:
            OLE_FREE(cast(context, c_void_p))

        final = values()
        final.SetStringValue(CONTEXT, transfer)
        chunks = bytearray()
        try:
            remaining = opened.GetUnsignedLargeIntegerValue(TOTAL_BYTES)
            chunk_size = max(1, min(opened.GetUnsignedIntegerValue(OPTIMAL), 1024 * 1024))
            if remaining > limit:
                raise WpdError("The camera transfer exceeds the configured size limit.")
            while remaining:
                length = min(remaining, chunk_size)
                chunk = values()
                chunk.SetStringValue(CONTEXT, transfer)
                chunk.SetUnsignedIntegerValue(REQUEST_BYTES, length)
                chunk.SetBufferValue(BUFFER, (c_ubyte * length)(), length)
                result = self._send(READ, chunk)
                actual = result.GetUnsignedIntegerValue(RECEIVED_BYTES)
                ptr, capacity = result.GetBufferValue(BUFFER)
                try:
                    if not 0 < actual <= min(length, capacity):
                        raise WpdError("Windows returned an incomplete camera transfer.")
                    chunks.extend(string_at(ptr, actual))
                finally:
                    OLE_FREE(ptr)
                remaining -= actual
        except (COMError, WpdError):
            with suppress(COMError, WpdError):
                self._send(FINISH, final)
            raise
        self._check(operation, self._send(FINISH, final))
        return bytes(chunks)
