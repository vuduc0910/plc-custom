"""PLC client using rk-mcprotocol — supports Mitsubishi FX5U (iQ-F) natively.

Replaces pymcprotocol which does not support iQ-F series.
Install: pip install rk-mcprotocol
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
        self._mc: Any = None  # rk_mcprotocol instance

    def connect(self) -> None:
        """Connect to the PLC via SLMP.

        Raises:
            PLCConnectionError: If connection fails after retries.
        """
        from rk_mcprotocol import mc_protocol  # noqa: I001

        with self._lock:
            if self._connected and self._mc is not None:
                logger.debug("RkSLMP PLC already connected")
                return

            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    mc = mc_protocol(ip=self._host, port=self._port)
                    self._mc = mc
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
            self._mc = None
            self._connected = False
        logger.info("RkSLMP PLC disconnected")

    def is_connected(self) -> bool:
        """Check if connected to the PLC."""
        with self._lock:
            return self._connected

    # --- Bit devices ---

    def read_bit(self, address: str) -> bool:
        """Read a single bit device (M, X, Y).

        Args:
            address: Device address, e.g. "M100".

        Returns:
            True if bit is ON, False if OFF.

        Raises:
            PLCError: If read fails.
        """
        device, number = self._parse_address(address)
        head = f"{device.lower()}{number}"

        with self._lock:
            mc = self._ensure_connected()
            try:
                values = mc.read_bit(headdevice=head, length=1)
                result = bool(values[0])
                logger.debug("RkSLMP read_bit {} = {}", address, result)
                return result
            except Exception as e:
                self._handle_comm_error(e, f"read_bit({address})")
                return False  # unreachable

    def write_bit(self, address: str, value: bool) -> None:
        """Write a single bit device.

        Args:
            address: Device address, e.g. "M200".
            value: True for ON, False for OFF.

        Raises:
            PLCError: If write fails.
        """
        device, number = self._parse_address(address)
        head = f"{device.lower()}{number}"

        with self._lock:
            mc = self._ensure_connected()
            try:
                mc.write_bit(headdevice=head, value=[1 if value else 0])
                logger.debug("RkSLMP write_bit {} = {}", address, value)
            except Exception as e:
                self._handle_comm_error(e, f"write_bit({address}, {value})")

    # --- Word devices ---

    def read_word(self, address: str) -> int:
        """Read a single word device (D, R).

        Args:
            address: Device address, e.g. "D100".

        Returns:
            16-bit word value.

        Raises:
            PLCError: If read fails.
        """
        device, number = self._parse_address(address)
        head = f"{device.lower()}{number}"

        with self._lock:
            mc = self._ensure_connected()
            try:
                values = mc.read_sign_word(headdevice=head, length=1, signed_type=True)
                result = values[0]
                logger.debug("RkSLMP read_word {} = {}", address, result)
                return int(result)
            except Exception as e:
                self._handle_comm_error(e, f"read_word({address})")
                return 0  # unreachable

    def write_word(self, address: str, value: int) -> None:
        """Write a single word device.

        Args:
            address: Device address, e.g. "D100".
            value: 16-bit integer value.

        Raises:
            PLCError: If write fails.
        """
        device, number = self._parse_address(address)
        head = f"{device.lower()}{number}"

        with self._lock:
            mc = self._ensure_connected()
            try:
                mc.write_sign_word(headdevice=head, value=[value])
                logger.debug("RkSLMP write_word {} = {}", address, value)
            except Exception as e:
                self._handle_comm_error(e, f"write_word({address}, {value})")

    def write_words(self, start_address: str, values: list[int]) -> None:
        """Write multiple consecutive word devices.

        Args:
            start_address: Starting device address, e.g. "D100".
            values: List of 16-bit integer values.

        Raises:
            PLCError: If write fails.
        """
        device, number = self._parse_address(start_address)
        head = f"{device.lower()}{number}"

        with self._lock:
            mc = self._ensure_connected()
            try:
                mc.write_sign_word(headdevice=head, value=values)
                logger.debug("RkSLMP write_words {} count={}", start_address, len(values))
            except Exception as e:
                self._handle_comm_error(e, f"write_words({start_address}, count={len(values)})")

    def write_float(self, address: str, value: float) -> None:
        """Write float as 2 consecutive D registers (IEEE 754, little-endian word order).

        Args:
            address: Starting device address, e.g. "D100".
            value: Float value to write.

        Raises:
            PLCError: If write fails.

        # TODO(client-Q6.1): Confirm word order with client.
        """
        device, number = self._parse_address(address)
        packed = struct.pack("<f", value)
        word_lo = int.from_bytes(packed[0:2], "little")
        word_hi = int.from_bytes(packed[2:4], "little")

        head = f"{device.lower()}{number}"
        with self._lock:
            mc = self._ensure_connected()
            try:
                mc.write_sign_word(headdevice=head, value=[word_lo, word_hi])
                logger.debug("RkSLMP write_float {} = {}", address, value)
            except Exception as e:
                self._handle_comm_error(e, f"write_float({address}, {value})")

    # --- Internal helpers ---

    @staticmethod
    def _parse_address(address: str) -> tuple[str, int]:
        """Parse a PLC address string into device and number.

        Args:
            address: e.g. "D100", "M200", "X10"

        Returns:
            Tuple of (device_letter, device_number).

        Raises:
            PLCAddressError: If address format is invalid.
        """
        match = _ADDRESS_PATTERN.match(address)
        if not match:
            raise PLCAddressError(f"Invalid PLC address: {address}")
        return match.group(1), int(match.group(2))

    def _ensure_connected(self) -> Any:
        """Return the MC instance, raising if not connected.

        Must be called with self._lock held.
        """
        if not self._connected or self._mc is None:
            raise PLCConnectionError("PLC not connected")
        return self._mc

    def _handle_comm_error(self, error: Exception, context: str) -> None:
        """Handle communication errors — mark disconnected and raise PLCError.

        Args:
            error: The original exception.
            context: Description of the operation that failed.
        """
        self._connected = False
        logger.error("RkSLMP PLC communication error in {}: {}", context, error)
        raise PLCError(f"PLC communication error in {context}: {error}") from error
