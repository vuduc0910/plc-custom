"""Fake PLC client for development and testing."""

import struct
import threading

from loguru import logger

from n1700_bridge.core.plc import PLCAddressError


class FakePLCClient:
    """In-memory PLC stub implementing PLCClient protocol.

    Thread-safe via Lock. Stores bit and word devices in dicts.
    """

    def __init__(self) -> None:
        self._bits: dict[str, bool] = {}
        self._words: dict[str, int] = {}
        self._lock = threading.Lock()
        self._connected = False

    def connect(self) -> None:
        """Simulate PLC connection."""
        with self._lock:
            self._connected = True
        logger.info("FakePLC connected")

    def disconnect(self) -> None:
        """Simulate PLC disconnection."""
        with self._lock:
            self._connected = False
        logger.info("FakePLC disconnected")

    def is_connected(self) -> bool:
        """Check if connected."""
        with self._lock:
            return self._connected

    def read_bit(self, address: str) -> bool:
        """Read a bit device."""
        self._validate_address(address)
        with self._lock:
            val = self._bits.get(address, False)
        logger.debug("FakePLC read_bit {} = {}", address, val)
        return val

    def write_bit(self, address: str, value: bool) -> None:
        """Write a bit device."""
        self._validate_address(address)
        with self._lock:
            self._bits[address] = value
        logger.debug("FakePLC write_bit {} = {}", address, value)

    def read_word(self, address: str) -> int:
        """Read a word device."""
        self._validate_address(address)
        with self._lock:
            val = self._words.get(address, 0)
        logger.debug("FakePLC read_word {} = {}", address, val)
        return val

    def write_word(self, address: str, value: int) -> None:
        """Write a word device."""
        self._validate_address(address)
        with self._lock:
            self._words[address] = value
        logger.debug("FakePLC write_word {} = {}", address, value)

    def write_words(self, start_address: str, values: list[int]) -> None:
        """Write multiple consecutive word devices."""
        self._validate_address(start_address)
        device = start_address[0]
        num = int(start_address[1:])
        with self._lock:
            for i, val in enumerate(values):
                addr = f"{device}{num + i}"
                self._words[addr] = val
        logger.debug("FakePLC write_words {} count={}", start_address, len(values))

    def write_float(self, address: str, value: float) -> None:
        """Write float as 2 consecutive D registers (IEEE 754, little-endian word order).

        # TODO(client-Q6.1): Confirm word order with client.
        """
        self._validate_address(address)
        packed = struct.pack("<f", value)
        word_lo = int.from_bytes(packed[0:2], "little")
        word_hi = int.from_bytes(packed[2:4], "little")
        device = address[0]
        num = int(address[1:])
        with self._lock:
            self._words[address] = word_lo
            self._words[f"{device}{num + 1}"] = word_hi
        logger.debug("FakePLC write_float {} = {}", address, value)

    # --- Test helpers ---

    def simulate_trigger(self, address: str = "M100") -> None:
        """Set trigger bit — used by tests and mock PLC UI."""
        with self._lock:
            self._bits[address] = True
        logger.info("FakePLC simulate_trigger {}", address)

    def get_all_bits(self) -> dict[str, bool]:
        """Return snapshot of all bit values (for test/debug)."""
        with self._lock:
            return dict(self._bits)

    def get_all_words(self) -> dict[str, int]:
        """Return snapshot of all word values (for test/debug)."""
        with self._lock:
            return dict(self._words)

    @staticmethod
    def _validate_address(address: str) -> None:
        """Validate PLC address format."""
        if len(address) < 2 or address[0] not in "DMRXY" or not address[1:].isdigit():
            raise PLCAddressError(f"Invalid PLC address: {address}")
