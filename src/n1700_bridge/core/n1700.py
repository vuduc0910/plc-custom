"""N1700 controller protocol and exceptions."""

from typing import Protocol


class N1700Error(Exception):
    """Base exception for N1700 operations."""


class N1700Controller(Protocol):
    """Protocol for controlling the N1700 desktop application."""

    def click_data_button(self) -> None:
        """Trigger N1700 app to export latest readings to Excel.

        Raises:
            N1700Error: If the window is not found or click fails.
        """
        ...

    def is_window_available(self) -> bool:
        """Check if the N1700 application window is available."""
        ...
