"""PLC client using rk-mcprotocol — supports Mitsubishi FX5U (iQ-F) natively.

Replaces pymcprotocol which does not support iQ-F series.
Install: pip install rk-mcprotocol

API: function-based, uses a socket object returned by open_socket().
"""

import re
import struct
import threading
import time
from typing import Any

from loguru import logger

from n1700_bridge.core.plc import PLCAddressError, PLCConnectionError, PLCError

_ADDRESS_PATTERN = re.compile(r"^([DMRXY])(\d+)$")
_MAX_RETRIES = 3
_BASE_RETRY_DELAY_S = 0.5


class RkSLMPPLCClient:
    """PLC client implementing PLCClient protocol via rk-mcprotocol.

    Designed for Mitsubishi FX5U (iQ-F series).
    Thread-safe via Lock. Retries on connection errors with exponential backoff.
    """

    def __init__(
        self,
        host: str = "192.168.1.10",
        port: int = 5007,
    ) -> None:
        self._host = host
        self._port = port
        self._lock = threading.Lock()
        self._connected = False
        self._sock: Any = None  # socket returned by open_socket()

    def connect(self) -> None:
        """Connect to the PLC via SLMP.

        Raises:
            PLCConnectionError: If connection fails after retries.
        """
        import rk_mcprotocol  # noqa: I001

        with self._lock:
            if self._connected and self._sock is not None:
                logger.debug("RkSLMP PLC already connected")
                return

            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    sock = rk_mcprotocol.open_socket(self._host, self._port)
                    self._sock = sock
                    self._connected = True
                    logger.info(
                        "RkSLMP PLC connected: {}:{} (attempt {})",
                        self._host, self._port, attempt,
                    )
                    return
                except Exception as e:
                    delay = _BASE_RETRY_DELAY_S * (2 ** (attempt - 1))
                    logger.warning(
                        "RkSLMP PLC connect attempt {}/{} failed: {} — retrying in {:.1f}s",
                        attempt, _MAX_RETRIES, e, delay,
                    )
                    if attempt < _MAX_RETRIES:
                        time.sleep(delay)

            raise PLCConnectionError(
                f"Failed to connect to PLC at {self._host}:{self._port} "
                f"after {_MAX_RETRIES} attempts"
            )

    def disconnect(self) -> None:
        """Disconnect from the PLC."""
        with self._lock:
            if self._sock is not None:
                try:
                    self._sock.close()
                except Exception as e:
                    logger.warning("Error closing PLC socket: {}", e)
                self._sock = None
            self._connected = False
        logger.info("RkSLMP PLC disconnected")

    def is_connected(self) -> bool:
        """Check if connected to the PLC."""
        with self._lock:
            return self._connected

    # --- Bit devices ---

    def read_bit(self, address: str) -> bool:
        """Read a single bit device (M, X, Y)."""
        import rk_mcprotocol

        device, number = self._parse_address(address)
        head = f"{device.lower()}{number}"

        with self._lock:
            sock = self._ensure_connected()
            try:
                values = rk_mcprotocol.read_bit(sock, head, 1)
                result = bool(values[0])
                logger.debug("RkSLMP read_bit {} = {}", address, result)
                return result
            except Exception as e:
                self._handle_comm_error(e, f"read_bit({address})")
                return False  # unreachable

    def write_bit(self, address: str, value: bool) -> None:
        """Write a single bit device."""
        import rk_mcprotocol

        device, number = self._parse_address(address)
        head = f"{device.lower()}{number}"

        with self._lock:
            sock = self._ensure_connected()
            try:
                rk_mcprotocol.write_bit(sock, head, [1 if value else 0])
                logger.debug("RkSLMP write_bit {} = {}", address, value)
            except Exception as e:
                self._handle_comm_error(e, f"write_bit({address}, {value})")

    # --- Word devices ---

    def read_word(self, address: str) -> int:
        """Read a single word device (D, R)."""
        import rk_mcprotocol

        device, number = self._parse_address(address)
        head = f"{device.lower()}{number}"

        with self._lock:
            sock = self._ensure_connected()
            try:
                values = rk_mcprotocol.read_sign_word(sock, head, 1, True)
                result = values[0]
                logger.debug("RkSLMP read_word {} = {}", address, result)
                return int(result)
            except Exception as e:
                self._handle_comm_error(e, f"read_word({address})")
                return 0  # unreachable

    def write_word(self, address: str, value: int) -> None:
        """Write a single word device."""
        import rk_mcprotocol

        device, number = self._parse_address(address)
        head = f"{device.lower()}{number}"

        with self._lock:
            sock = self._ensure_connected()
            try:
                rk_mcprotocol.write_sign_word(sock, head, [value], True)
                logger.debug("RkSLMP write_word {} = {}", address, value)
            except Exception as e:
                self._handle_comm_error(e, f"write_word({address}, {value})")

    def write_words(self, start_address: str, values: list[int]) -> None:
        """Write multiple consecutive word devices."""
        import rk_mcprotocol

        device, number = self._parse_address(start_address)
        head = f"{device.lower()}{number}"

        with self._lock:
            sock = self._ensure_connected()
            try:
                rk_mcprotocol.write_sign_word(sock, head, values, True)
                logger.debug("RkSLMP write_words {} count={}", start_address, len(values))
            except Exception as e:
                self._handle_comm_error(e, f"write_words({start_address}, count={len(values)})")

    def write_float(self, address: str, value: float) -> None:
        """Write float as 2 consecutive D registers (IEEE 754, little-endian word order)."""
        import rk_mcprotocol

        device, number = self._parse_address(address)
        packed = struct.pack("<f", value)
        word_lo = int.from_bytes(packed[0:2], "little")
        word_hi = int.from_bytes(packed[2:4], "little")

        head = f"{device.lower()}{number}"
        with self._lock:
            sock = self._ensure_connected()
            try:
                rk_mcprotocol.write_sign_word(sock, head, [word_lo, word_hi], True)
                logger.debug("RkSLMP write_float {} = {}", address, value)
            except Exception as e:
                self._handle_comm_error(e, f"write_float({address}, {value})")

    # --- Internal helpers ---

    @staticmethod
    def _parse_address(address: str) -> tuple[str, int]:
        """Parse a PLC address string into device and number."""
        match = _ADDRESS_PATTERN.match(address)
        if not match:
            raise PLCAddressError(f"Invalid PLC address: {address}")
        return match.group(1), int(match.group(2))

    def _ensure_connected(self) -> Any:
        """Return the socket, auto-reconnecting if needed. Must hold self._lock."""
        if self._connected and self._sock is not None:
            return self._sock

        # Auto-reconnect
        import rk_mcprotocol
        try:
            logger.info("RkSLMP PLC auto-reconnecting to {}:{}...", self._host, self._port)
            if self._sock is not None:
                try:
                    self._sock.close()
                except Exception:
                    pass
            sock = rk_mcprotocol.open_socket(self._host, self._port)
            self._sock = sock
            self._connected = True
            logger.info("RkSLMP PLC auto-reconnected successfully")
            return self._sock
        except Exception as e:
            self._connected = False
            self._sock = None
            raise PLCConnectionError(
                f"PLC auto-reconnect failed: {e}"
            ) from e

    def _handle_comm_error(self, error: Exception, context: str) -> None:
        """Handle communication errors — mark disconnected and raise PLCError."""
        self._connected = False
        logger.error("RkSLMP PLC communication error in {}: {}", context, error)
        raise PLCError(f"PLC communication error in {context}: {error}") from error

