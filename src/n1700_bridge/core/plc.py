"""PLC client protocol and exceptions."""

from typing import Protocol, runtime_checkable


class PLCError(Exception):
    """Base exception for PLC operations."""


class PLCConnectionError(PLCError):
    """Raised when PLC connection fails."""


class PLCAddressError(PLCError):
    """Raised when an invalid PLC address is used."""


@runtime_checkable
class PLCClient(Protocol):
    """Protocol for PLC communication.

    Address format: "D100", "M200", etc.
    Validated with regex in adapters.
    """

    def connect(self) -> None:
        """Connect to the PLC."""
        ...

    def disconnect(self) -> None:
        """Disconnect from the PLC."""
        ...

    def is_connected(self) -> bool:
        """Check if connected to the PLC."""
        ...

    # Bit devices (M, X, Y)
    def read_bit(self, address: str) -> bool:
        """Read a single bit device."""
        ...

    def write_bit(self, address: str, value: bool) -> None:
        """Write a single bit device."""
        ...

    # Word devices (D, R)
    def read_word(self, address: str) -> int:
        """Read a single word device."""
        ...

    def write_word(self, address: str, value: int) -> None:
        """Write a single word device."""
        ...

    def write_words(self, start_address: str, values: list[int]) -> None:
        """Write multiple consecutive word devices."""
        ...

    def write_float(self, address: str, value: float) -> None:
        """Write a float as 2 consecutive D registers (IEEE 754).

        # TODO(client-Q6.1): Confirm word order (little-endian) with client.
        """
        ...
