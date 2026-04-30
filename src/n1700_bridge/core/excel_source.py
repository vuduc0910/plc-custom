"""Excel data source protocol and exceptions."""

from datetime import datetime
from typing import Protocol

from .models import PortReading


class ExcelSourceError(Exception):
    """Base exception for Excel source operations."""


class ExcelDataSource(Protocol):
    """Protocol for reading measurement data from an Excel file."""

    def read_latest_row(self) -> list[PortReading]:
        """Return readings for ports 1..9 from the last data row.

        Raises:
            ExcelSourceError: If file is closed, corrupt, or empty.
        """
        ...

    def get_last_row_timestamp(self) -> datetime:
        """Return the timestamp of the last data row."""
        ...
