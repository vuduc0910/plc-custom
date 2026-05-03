"""Direct N1700 access via the vendor-supplied native DLL (N1700.dll / N1700_64.dll).

This bypasses the MillimarN1700.exe GUI + Excel export loop entirely:
we call ``N1700PollData`` for each channel and get the measuring value
as a ``double`` — no window clicks, no file I/O, no settling delay.

The vendor SDK lives at:
    Millimar--N1700--SW-2024-07-31/Millimar N1700 DLL  1.02.14/
        Win32/N1700.dll
        Win64/N1700_64.dll
        N1700.h        (C API header)

FTDI USB driver CDM21224 must be installed on the target Windows machine.
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

# --- Return codes from N1700.h ---
_N1700_SUCCESS = 0
_RETURN_CODE_MESSAGES: dict[int, str] = {
    0: "SUCCESS",
    -1: "FAILURE",
    -2: "TIMEOUT",
    -3: "INVALID_DEVNO",
    -4: "NO_MODULES",
    -5: "FILENOTEXISTS",
    -6: "WRONGFILEFORMAT",
    -7: "NOTYETSUPPORTED",
    -8: "INVALID_CHANNELIDX",
    -9: "CONTINUOUS_ACTIVE",
    -10: "CALL_STILL_IN_ACTION",
    -11: "WRONG_MODULETYPE",
    -12: "FILEVARIANTNOTEXISTS",
}


def _rc_message(rc: int) -> str:
    return _RETURN_CODE_MESSAGES.get(rc, f"UNKNOWN({rc})")


def _is_windows() -> bool:
    return sys.platform.startswith("win")


class N1700DllClient:
    """Thin thread-safe wrapper around N1700.dll.

    Lifecycle:
        >>> client = N1700DllClient(dll_path=Path("N1700.dll"))
        >>> client.connect()
        >>> value = client.poll_data(channel_idx=0)
        >>> client.disconnect()

    Construction does NOT load the DLL — :meth:`connect` does.
    Pass ``dll=<mock>`` to inject a fake library object for testing on
    non-Windows platforms.
    """

    def __init__(
        self,
        dll_path: Path | str = "N1700.dll",
        *,
        dll: Any = None,
    ) -> None:
        self._dll_path = Path(dll_path)
        self._dll: Any = dll  # injected or lazily loaded
        self._lock = threading.Lock()
        self._connected = False
        self._num_modules = 0
        self._num_channels = 0

    # --- Lifecycle ---

    def connect(self) -> None:
        """Load DLL and call ``N1700InitializeLibrary``.

        Raises:
            N1700Error: If the DLL cannot be loaded or initialization fails.
        """
        with self._lock:
            if self._connected:
                return

            if self._dll is None:
                self._dll = self._load_dll()
                self._configure_signatures(self._dll)

            num_modules = ctypes.c_uint32(0)
            num_channels = ctypes.c_uint32(0)
            rc = self._dll.N1700InitializeLibrary(
                False,  # Console
                ctypes.byref(num_modules),
                ctypes.byref(num_channels),
                0,  # Par
            )
            if rc != _N1700_SUCCESS:
                raise N1700Error(
                    f"N1700InitializeLibrary failed: {_rc_message(rc)}"
                )

            self._num_modules = num_modules.value
            self._num_channels = num_channels.value
            self._connected = True

            logger.info(
                "N1700DllClient connected: {} modules, {} channels",
                self._num_modules, self._num_channels,
            )

    def disconnect(self) -> None:
        """Call ``N1700FreeLibrary``."""
        with self._lock:
            if not self._connected or self._dll is None:
                return
            try:
                self._dll.N1700FreeLibrary()
            except Exception as e:
                logger.warning("N1700FreeLibrary raised: {}", e)
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

    # --- Data ---

    def poll_data(self, channel_idx: int) -> float:
        """Read the current measuring value of a channel.

        Raises:
            N1700Error: If not connected or the DLL call fails.
        """
        with self._lock:
            if not self._connected or self._dll is None:
                raise N1700Error("N1700 DLL not connected")
            value = ctypes.c_double(0.0)
            rc = self._dll.N1700PollData(
                ctypes.c_uint32(channel_idx),
                ctypes.byref(value),
            )
            if rc != _N1700_SUCCESS:
                raise N1700Error(
                    f"N1700PollData({channel_idx}) failed: {_rc_message(rc)}"
                )
            return float(value.value)

    # --- Internal ---

    def _load_dll(self) -> Any:
        if not _is_windows():
            raise N1700Error(
                "N1700 DLL is Windows-only (ctypes.WinDLL unavailable). "
                "Use fake mode on macOS/Linux for development."
            )
        path = self._dll_path
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            raise N1700Error(f"N1700 DLL not found at {path}")
        try:
            # N1700.dll uses __stdcall → WinDLL
            return ctypes.WinDLL(str(path))  # type: ignore[attr-defined]
        except OSError as e:
            raise N1700Error(f"Failed to load {path}: {e}") from e

    @staticmethod
    def _configure_signatures(dll: Any) -> None:
        """Set argtypes/restype for the subset of functions we call.

        Matches the signatures declared in ``N1700.h`` (vendor SDK).
        """
        dll.N1700InitializeLibrary.argtypes = [
            ctypes.c_bool,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_int32,
        ]
        dll.N1700InitializeLibrary.restype = ctypes.c_int

        dll.N1700FreeLibrary.argtypes = []
        dll.N1700FreeLibrary.restype = ctypes.c_int

        dll.N1700PollData.argtypes = [
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_double),
        ]
        dll.N1700PollData.restype = ctypes.c_int


class DllN1700Controller:
    """N1700Controller implementation backed by the native DLL.

    Because the DLL streams live values, there is no "export to Excel" step
    to trigger — :meth:`click_data_button` is a no-op that succeeds as long
    as the DLL is connected.
    """

    def __init__(self, client: N1700DllClient) -> None:
        self._client = client

    def click_data_button(self) -> None:
        """No-op: data is already live via ``N1700PollData``."""
        if not self._client.is_connected():
            raise N1700Error("N1700 DLL not connected")
        logger.debug("DllN1700Controller click_data_button (no-op)")

    def is_window_available(self) -> bool:
        """Report connection status; the GUI window is not used."""
        return self._client.is_connected()


class DllN1700Source:
    """ExcelDataSource implementation backed by the native DLL.

    ``read_latest_row`` polls channels ``0..channel_count-1`` and maps them
    to ports ``1..channel_count``.
    """

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
        """Poll all configured channels and return PortReadings.

        Raises:
            ExcelSourceError: If polling fails (wrapped for protocol compat).
        """
        if not self._client.is_connected():
            raise ExcelSourceError("N1700 DLL not connected")

        readings: list[PortReading] = []
        for i in range(self._channel_count):
            ch = self._channel_start + i
            try:
                value = self._client.poll_data(ch)
            except N1700Error as e:
                raise ExcelSourceError(
                    f"Failed to poll channel {ch}: {e}"
                ) from e
            readings.append(PortReading(port=i + 1, value=value))

        logger.debug(
            "DllN1700Source polled {} channels via DLL",
            self._channel_count,
        )
        return readings

    def get_last_row_timestamp(self) -> datetime:
        """Return current time — DLL data is always 'just now'."""
        return datetime.now()

    def is_file_available(self) -> bool:
        """Check DLL connection status (matches Excel-source semantics)."""
        return self._client.is_connected()
