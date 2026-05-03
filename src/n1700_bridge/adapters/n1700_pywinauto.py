"""Real N1700 controller using pywinauto for UI automation.

Automates clicking the "Data" button in the N1700 desktop application.
Falls back to pixel coordinates if the button control cannot be found.
"""

import re
from typing import Any

from loguru import logger

from n1700_bridge.core.n1700 import N1700Error


class PywinautoN1700Controller:
    """Controls the N1700 desktop application via pywinauto.

    Finds the N1700 window by title regex and clicks the "Data" button
    to trigger measurement data export to Excel.
    """

    def __init__(
        self,
        window_title_regex: str = "N1700.*",
        button_name: str = "Data",
        fallback_coords: tuple[int, int] | None = None,
    ) -> None:
        self._title_re = window_title_regex
        self._button_name = button_name
        self._fallback_coords = fallback_coords
        self._app: Any = None
        self._window: Any = None

    def click_data_button(self) -> None:
        """Click the Data button in the N1700 application.

        Strategy:
            1. Find the N1700 window by title regex
            2. Find ALL "Data" buttons and click the rightmost one (channel 0)
            3. If not found by control name, try title regex
            4. If both fail, fall back to pixel coordinates

        Raises:
            N1700Error: If the window is not found or click fails.
        """
        from pywinauto.application import Application  # noqa: I001

        window = self._find_window(Application)
        if window is None:
            raise N1700Error(
                f"N1700 window not found (title_re={self._title_re!r})"
            )

        # Strategy 1: Find ALL "Data" buttons, pick rightmost (channel 0)
        try:
            buttons = window.children(
                title=self._button_name,
                control_type="Button",
            )
            if buttons:
                # Sort by x-coordinate (left position), pick the rightmost
                rightmost = max(buttons, key=lambda b: b.rectangle().left)
                rightmost.click_input()
                logger.info(
                    "N1700 clicked rightmost '{}' button (x={}) out of {} buttons",
                    self._button_name,
                    rightmost.rectangle().left,
                    len(buttons),
                )
                return
        except Exception as e:
            logger.debug(
                "Button '{}' not found by control name: {}",
                self._button_name, e,
            )

        # Strategy 2: Try by title match (less strict)
        try:
            buttons = window.children(
                title_re=f".*{re.escape(self._button_name)}.*",
            )
            if buttons:
                rightmost = max(buttons, key=lambda b: b.rectangle().left)
                rightmost.click_input()
                logger.info(
                    "N1700 clicked rightmost '{}' button via title regex (x={})",
                    self._button_name,
                    rightmost.rectangle().left,
                )
                return
        except Exception as e:
            logger.debug(
                "Button '{}' not found by title regex: {}",
                self._button_name, e,
            )

        # Strategy 3: Fallback to pixel coordinates
        if self._fallback_coords is not None:
            x, y = self._fallback_coords
            try:
                window.click_input(coords=(x, y))
                logger.warning(
                    "N1700 clicked at fallback coords ({}, {}) — "
                    "consider finding the proper button control",
                    x, y,
                )
                return
            except Exception as e:
                logger.error("N1700 fallback click failed: {}", e)
                raise N1700Error(
                    f"N1700 fallback click at ({x}, {y}) failed: {e}"
                ) from e

        raise N1700Error(
            f"Could not find or click '{self._button_name}' button in N1700 window. "
            "Set fallback_coords in config as a workaround."
        )

    def is_window_available(self) -> bool:
        """Check if the N1700 application window is visible.

        Returns:
            True if the window is found and visible.
        """
        try:
            from pywinauto.application import Application  # noqa: I001

            window = self._find_window(Application)
            return window is not None
        except Exception:
            return False

    def _find_window(self, application_cls: type) -> Any:
        """Find the N1700 window by title regex.

        Tries UIA backend first (better for modern apps), falls back to win32.

        Args:
            application_cls: The pywinauto Application class.

        Returns:
            The window wrapper object, or None if not found.
        """
        # Try UIA backend first
        for backend in ("uia", "win32"):
            try:
                app = application_cls(backend=backend)
                app.connect(title_re=self._title_re, timeout=2)
                window = app.window(title_re=self._title_re)
                if window.exists(timeout=1):
                    self._app = app
                    self._window = window
                    logger.debug(
                        "N1700 window found via {} backend: {}",
                        backend, window.window_text(),
                    )
                    return window
            except Exception as e:
                logger.debug(
                    "N1700 window search failed with {} backend: {}",
                    backend, e,
                )
                continue

        logger.warning("N1700 window not found with any backend")
        return None
