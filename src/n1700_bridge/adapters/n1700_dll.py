"""N1700 DLL adapter using continuous data streaming.

Uses N1700StartContinuousRequestAllData + RegisterExtDataCallback
instead of per-channel N1700PollData calls.

SDK: Millimar--N1700--SW-2024-07-31/Millimar N1700 DLL 1.02.14/
FTDI USB driver CDM21224 required on target Windows machine.
"""

from __future__ import annotations

import ctypes
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from n1700_bridge.core.excel_source import ExcelSourceError
from n1700_bridge.core.models import PortReading
from n1700_bridge.core.n1700 import N1700Error

_N1700_SUCCESS = 0
_RETURN_CODE_MESSAGES: dict[int, str] = {
    0: "SUCCESS", -1: "FAILURE", -2: "TIMEOUT", -3: "INVALID_DEVNO",
    -4: "NO_MODULES", -5: "FILENOTEXISTS", -6: "WRONGFILEFORMAT",
    -7: "NOTYETSUPPORTED", -8: "INVALID_CHANNELIDX", -9: "CONTINUOUS_ACTIVE",
    -10: "CALL_STILL_IN_ACTION", -11: "WRONG_MODULETYPE",
    -12: "FILEVARIANTNOTEXISTS",
}


def _rc_msg(rc: int) -> str:
    return _RETURN_CODE_MESSAGES.get(rc, f"UNKNOWN({rc})")


class N1700ChannelExtData(ctypes.Structure):
    _fields_ = [
        ("channel_idx", ctypes.c_uint32),
        ("value_type", ctypes.c_byte),
        ("_reserve1", ctypes.c_byte * 3),
        ("d_value", ctypes.c_double),
        ("reference_active", ctypes.c_byte),
        ("referenced", ctypes.c_byte),
        ("_reserve2", ctypes.c_byte * 14),
    ]


_CbFactory = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
ExtDataCbType = _CbFactory(
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(N1700ChannelExtData),
    ctypes.c_void_p,
)


class N1700DllClient:
    def __init__(
        self,
        dll_path: Path | str = "N1700.dll",
        *,
        dll: Any = None,
    ) -> None:
        self._dll_path = Path(dll_path)
        self._dll: Any = dll
        self._lock = threading.Lock()
        self._connected = False
        self._num_modules = 0
        self._num_channels = 0
        self._continuous_active = False
        self._callback_ref: Any = None
        self._latest_values: dict[int, float] = {}
        self._values_lock = threading.Lock()

    def connect(self) -> None:
        with self._lock:
            if self._connected:
                return
            if self._dll is None:
                self._dll = self._load_dll()
            _configure_signatures(self._dll)

            num_mod = ctypes.c_uint32(0)
            num_ch = ctypes.c_uint32(0)
            rc = self._dll.N1700InitializeLibrary(
                False, ctypes.byref(num_mod), ctypes.byref(num_ch), 0,
            )
            if rc != _N1700_SUCCESS:
                raise N1700Error(f"N1700InitializeLibrary failed: {_rc_msg(rc)}")

            self._num_modules = num_mod.value
            self._num_channels = num_ch.value
            self._connected = True
            logger.info(
                "N1700DllClient connected: {} modules, {} channels",
                self._num_modules, self._num_channels,
            )
            self._start_continuous()

    def _start_continuous(self) -> None:
        ch_arr = (ctypes.c_int * self._num_channels)(
            *range(self._num_channels)
        )
        self._callback_ref = ExtDataCbType(self._on_data)
        ctx = ctypes.c_int(0)

        rc = self._dll.N1700RegisterExtDataCallback(
            self._callback_ref, self._num_channels, ch_arr, ctypes.byref(ctx),
        )
        if rc != _N1700_SUCCESS:
            logger.warning("RegisterExtDataCallback failed: {}", _rc_msg(rc))
            return

        rc = self._dll.N1700RequestAllData(0)
        if rc != _N1700_SUCCESS:
            logger.warning("RequestAllData initial snapshot failed: {}", _rc_msg(rc))

        rc = self._dll.N1700StartContinuousRequestAllData(
            ctypes.c_uint32(0), ctypes.c_int(0),
        )
        if rc != _N1700_SUCCESS:
            logger.warning("StartContinuousRequestAllData failed: {}", _rc_msg(rc))
            return

        self._continuous_active = True
        logger.info("Continuous data streaming started")

    def _on_data(self, num_data: int, p_data: Any, _ctx: Any) -> int:
        with self._values_lock:
            for i in range(num_data):
                entry = p_data[i]
                if entry.value_type == 1:
                    self._latest_values[entry.channel_idx] = entry.d_value
        return 0

    def disconnect(self) -> None:
        with self._lock:
            if not self._connected or self._dll is None:
                return
            try:
                if self._continuous_active:
                    self._dll.N1700StopContinuousRequestAllData()
                    self._continuous_active = False
                if self._callback_ref is not None:
                    self._dll.N1700UnregisterExtDataCallback(self._callback_ref)
                    self._callback_ref = None
                self._dll.N1700FreeLibrary()
            except Exception as e:
                logger.warning("Error during N1700 disconnect: {}", e)
            self._connected = False
            logger.info("N1700DllClient disconnected")

    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    @property
    def num_channels(self) -> int:
        with self._lock:
            return self._num_channels

    @property
    def num_modules(self) -> int:
        with self._lock:
            return self._num_modules

    def get_latest_values(self) -> dict[int, float]:
        with self._values_lock:
            return dict(self._latest_values)

    def poll_data(self, channel_idx: int) -> float:
        with self._lock:
            if not self._connected or self._dll is None:
                raise N1700Error("N1700 DLL not connected")
            value = ctypes.c_double(0.0)
            rc = self._dll.N1700PollData(
                ctypes.c_uint32(channel_idx), ctypes.byref(value),
            )
            if rc != _N1700_SUCCESS:
                raise N1700Error(
                    f"N1700PollData({channel_idx}) failed: {_rc_msg(rc)}"
                )
            return float(value.value)

    def _load_dll(self) -> Any:
        if not sys.platform.startswith("win"):
            raise N1700Error(
                "N1700 DLL is Windows-only. "
                "Use fake mode on macOS/Linux for development."
            )
        path = self._dll_path
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            raise N1700Error(f"N1700 DLL not found at {path}")
        try:
            return ctypes.WinDLL(str(path))  # type: ignore[attr-defined]
        except OSError as e:
            raise N1700Error(f"Failed to load {path}: {e}") from e


def _configure_signatures(dll: Any) -> None:
    dll.N1700InitializeLibrary.argtypes = [
        ctypes.c_bool, ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32), ctypes.c_int32,
    ]
    dll.N1700InitializeLibrary.restype = ctypes.c_int

    dll.N1700FreeLibrary.argtypes = []
    dll.N1700FreeLibrary.restype = ctypes.c_int

    dll.N1700PollData.argtypes = [
        ctypes.c_uint32, ctypes.POINTER(ctypes.c_double),
    ]
    dll.N1700PollData.restype = ctypes.c_int

    dll.N1700RequestAllData.argtypes = [ctypes.c_int]
    dll.N1700RequestAllData.restype = ctypes.c_int

    dll.N1700RegisterExtDataCallback.argtypes = [
        ExtDataCbType, ctypes.c_int,
        ctypes.POINTER(ctypes.c_int), ctypes.c_void_p,
    ]
    dll.N1700RegisterExtDataCallback.restype = ctypes.c_int

    dll.N1700UnregisterExtDataCallback.argtypes = [ExtDataCbType]
    dll.N1700UnregisterExtDataCallback.restype = ctypes.c_int

    dll.N1700StartContinuousRequestAllData.argtypes = [
        ctypes.c_uint32, ctypes.c_int,
    ]
    dll.N1700StartContinuousRequestAllData.restype = ctypes.c_int

    dll.N1700StopContinuousRequestAllData.argtypes = []
    dll.N1700StopContinuousRequestAllData.restype = ctypes.c_int


class DllN1700Controller:
    def __init__(self, client: N1700DllClient) -> None:
        self._client = client

    def click_data_button(self) -> None:
        if not self._client.is_connected():
            raise N1700Error("N1700 DLL not connected")

    def is_window_available(self) -> bool:
        return self._client.is_connected()


class DllN1700Source:
    def __init__(
        self,
        client: N1700DllClient,
        channel_count: int = 9,
        channel_start_index: int = 1,
    ) -> None:
        self._client = client
        self._channel_count = channel_count
        self._channel_start = channel_start_index

    def read_latest_row(self) -> list[PortReading]:
        if not self._client.is_connected():
            raise ExcelSourceError("N1700 DLL not connected")

        latest = self._client.get_latest_values()
        readings: list[PortReading] = []
        for i in range(self._channel_count):
            ch = self._channel_start + i
            value = latest.get(ch, 0.0)
            if ch not in latest:
                logger.warning("Channel {} has no data yet", ch)
            readings.append(PortReading(port=i + 1, value=value))

        logger.debug(
            "DllN1700Source read {} channels from continuous stream",
            self._channel_count,
        )
        return readings

    def get_last_row_timestamp(self) -> datetime:
        return datetime.now()

    def is_file_available(self) -> bool:
        return self._client.is_connected()
