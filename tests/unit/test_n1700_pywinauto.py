"""Tests for PywinautoN1700Controller adapter.

Note: pywinauto is Windows-only. Tests mock the import at module level
so they can run on any platform (macOS, Linux, CI).
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock pywinauto before importing the adapter (Windows-only module)
_mock_pywinauto = MagicMock()
sys.modules["pywinauto"] = _mock_pywinauto
sys.modules["pywinauto.application"] = _mock_pywinauto.application

from n1700_bridge.adapters.n1700_pywinauto import PywinautoN1700Controller  # noqa: E402
from n1700_bridge.core.n1700 import N1700Error  # noqa: E402


class TestWindowSearch:
    """Tests for window finding logic."""

    def test_is_window_available_returns_false_when_not_found(self) -> None:
        """Should return False when no N1700 window exists."""
        controller = PywinautoN1700Controller(window_title_regex="N1700.*")

        with patch.object(controller, "_find_window", return_value=None):
            assert controller.is_window_available() is False

    def test_is_window_available_returns_true_when_found(self) -> None:
        """Should return True when N1700 window is found."""
        controller = PywinautoN1700Controller(window_title_regex="N1700.*")
        mock_window = MagicMock()

        with patch.object(controller, "_find_window", return_value=mock_window):
            assert controller.is_window_available() is True


class TestClickDataButton:
    """Tests for the click_data_button logic."""

    def test_raises_when_window_not_found(self) -> None:
        """Should raise N1700Error when window is not found."""
        controller = PywinautoN1700Controller(window_title_regex="N1700.*")

        with patch.object(controller, "_find_window", return_value=None):
            with pytest.raises(N1700Error, match="not found"):
                controller.click_data_button()

    def test_clicks_button_by_control_name(self) -> None:
        """Should click button when found by control name."""
        controller = PywinautoN1700Controller(button_name="Data")
        mock_window = MagicMock()
        mock_button = MagicMock()
        mock_button.exists.return_value = True
        mock_window.child_window.return_value = mock_button

        with patch.object(controller, "_find_window", return_value=mock_window):
            controller.click_data_button()

        mock_button.click_input.assert_called_once()

    def test_fallback_to_coords_when_button_not_found(self) -> None:
        """Should use fallback_coords when button cannot be found."""
        controller = PywinautoN1700Controller(
            button_name="Data",
            fallback_coords=(500, 300),
        )
        mock_window = MagicMock()
        # Both child_window strategies fail
        mock_window.child_window.side_effect = Exception("not found")

        with patch.object(controller, "_find_window", return_value=mock_window):
            controller.click_data_button()

        mock_window.click_input.assert_called_once_with(coords=(500, 300))

    def test_raises_when_no_button_and_no_fallback(self) -> None:
        """Should raise N1700Error when button not found and no fallback coords."""
        controller = PywinautoN1700Controller(
            button_name="Data",
            fallback_coords=None,
        )
        mock_window = MagicMock()
        mock_window.child_window.side_effect = Exception("not found")

        with patch.object(controller, "_find_window", return_value=mock_window):
            with pytest.raises(N1700Error, match="Could not find or click"):
                controller.click_data_button()

    def test_raises_when_fallback_click_fails(self) -> None:
        """Should raise N1700Error when fallback click also fails."""
        controller = PywinautoN1700Controller(
            button_name="Data",
            fallback_coords=(500, 300),
        )
        mock_window = MagicMock()
        mock_window.child_window.side_effect = Exception("not found")
        mock_window.click_input.side_effect = Exception("click failed")

        with patch.object(controller, "_find_window", return_value=mock_window):
            with pytest.raises(N1700Error, match="fallback click"):
                controller.click_data_button()


class TestConfiguration:
    """Tests for controller configuration."""

    def test_default_config(self) -> None:
        """Should have sensible defaults."""
        controller = PywinautoN1700Controller()
        assert controller._title_re == "N1700.*"
        assert controller._button_name == "Data"
        assert controller._fallback_coords is None

    def test_custom_config(self) -> None:
        """Should accept custom configuration."""
        controller = PywinautoN1700Controller(
            window_title_regex="Custom.*",
            button_name="Measure",
            fallback_coords=(100, 200),
        )
        assert controller._title_re == "Custom.*"
        assert controller._button_name == "Measure"
        assert controller._fallback_coords == (100, 200)
