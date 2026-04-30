"""Mock PLC Control Panel — PySide6 dialog for manual testing.

Run: python -m mocks.plc_control_panel

Provides:
- "Fire trigger M100" button
- Live view of D100..D118 and M200..M202
"""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

# We need to import the running app's FakePLCClient.
# This panel connects to the same instance via shared memory file or IPC.
# For simplicity in POC, we run this in-process via a shared reference.
# In standalone mode, we create our own FakePLCClient.
from n1700_bridge.adapters.plc_fake import FakePLCClient


class PLCControlPanel(QWidget):
    """Mock PLC control panel for development testing."""

    def __init__(self, plc: FakePLCClient) -> None:
        super().__init__()
        self._plc = plc
        self.setWindowTitle("Mock PLC Control Panel")
        self.setMinimumSize(500, 400)

        self._setup_ui()
        self._start_refresh_timer()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Fire trigger button
        self.trigger_btn = QPushButton("Fire trigger M100")
        self.trigger_btn.setStyleSheet(
            "QPushButton { background-color: #ff5722; color: white; "
            "font-size: 16px; padding: 12px; font-weight: bold; }"
        )
        self.trigger_btn.clicked.connect(self._fire_trigger)
        layout.addWidget(self.trigger_btn)

        # D registers group
        d_group = QGroupBox("Word Registers (D100..D118)")
        d_layout = QVBoxLayout(d_group)
        self._d_labels: dict[str, QLabel] = {}
        for i in range(100, 119):
            addr = f"D{i}"
            label = QLabel(f"{addr}: 0")
            label.setStyleSheet("font-family: monospace; font-size: 12px;")
            self._d_labels[addr] = label
            d_layout.addWidget(label)

        d_scroll = QScrollArea()
        d_scroll.setWidget(d_group)
        d_scroll.setWidgetResizable(True)

        # M registers group
        m_group = QGroupBox("Bit Registers (M200..M202)")
        m_layout = QVBoxLayout(m_group)
        self._m_labels: dict[str, QLabel] = {}
        for i in range(200, 203):
            addr = f"M{i}"
            label = QLabel(f"{addr}: False")
            label.setStyleSheet("font-family: monospace; font-size: 12px;")
            self._m_labels[addr] = label
            m_layout.addWidget(label)

        # Horizontal layout for both groups
        groups_layout = QHBoxLayout()
        groups_layout.addWidget(d_scroll)
        groups_layout.addWidget(m_group)
        layout.addLayout(groups_layout)

    def _fire_trigger(self) -> None:
        """Set M100 trigger bit to True."""
        self._plc.simulate_trigger("M100")

    def _start_refresh_timer(self) -> None:
        """Refresh register display every 200ms."""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_display)
        self._timer.start(200)

    def _refresh_display(self) -> None:
        """Update all register labels from FakePLCClient state."""
        words = self._plc.get_all_words()
        for addr, label in self._d_labels.items():
            val = words.get(addr, 0)
            label.setText(f"{addr}: {val}")

        bits = self._plc.get_all_bits()
        for addr, label in self._m_labels.items():
            val = bits.get(addr, False)
            color = "#4caf50" if val else "#9e9e9e"
            label.setText(f"{addr}: {val}")
            label.setStyleSheet(
                f"font-family: monospace; font-size: 12px; color: {color};"
            )


def main() -> None:
    """Launch the standalone PLC control panel."""
    app = QApplication(sys.argv)

    # Create standalone FakePLCClient
    plc = FakePLCClient()
    plc.connect()

    panel = PLCControlPanel(plc)
    panel.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
