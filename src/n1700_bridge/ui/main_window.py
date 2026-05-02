"""Main application window matching spec slide 5 layout."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .resources.strings_vi import STRINGS

if TYPE_CHECKING:
    from n1700_bridge.config.models import RegisterConfig
    from n1700_bridge.core.n1700 import N1700Controller
    from n1700_bridge.core.plc import PLCClient
    from n1700_bridge.services.measurement_service import MeasurementService
    from n1700_bridge.services.register_manager import RegisterManager

_ADDRESS_REGEX_PATTERN = r"^[DMRXY]\d+$"
_NUM_PORTS = 9
_NUM_GROUPS = 3
_PORTS_PER_GROUP = 3


class MainWindow(QMainWindow):
    """Main window for N1700 Bridge application."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(STRINGS["window_title"])
        self.setMinimumSize(900, 500)

        self._setup_ui()
        self._setup_status_bar()
        self._load_stylesheet()

    def _setup_ui(self) -> None:
        """Build the main UI layout."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # --- Top bar: barcode + export ---
        top_bar = QHBoxLayout()
        barcode_label = QLabel(STRINGS["part_id_label"])
        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText(STRINGS["barcode_placeholder"])
        self.barcode_input.setMinimumWidth(250)

        self.barcode_reset_btn = QPushButton(STRINGS["barcode_reset_btn"])
        self.barcode_reset_btn.setObjectName("reset-btn")

        self.export_btn = QPushButton(STRINGS["export_btn"])
        self.export_btn.setObjectName("export-btn")

        top_bar.addWidget(barcode_label)
        top_bar.addWidget(self.barcode_input)
        top_bar.addWidget(self.barcode_reset_btn)
        top_bar.addStretch()
        top_bar.addWidget(self.export_btn)
        main_layout.addLayout(top_bar)

        # --- Measurement table (9 ports) ---
        self.measurement_table = QTableWidget(0, _NUM_PORTS + 1)  # Time + 9 ports
        headers = [STRINGS["time_column"]] + [str(i) for i in range(1, _NUM_PORTS + 1)]
        self.measurement_table.setHorizontalHeaderLabels(headers)
        self.measurement_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.measurement_table.setMinimumHeight(150)
        main_layout.addWidget(self.measurement_table)

        # --- Register addresses + Judgments grid ---
        grid = QGridLayout()

        # Row 0: Register address label + port address inputs + Save button
        grid.addWidget(QLabel(STRINGS["register_address_label"]), 0, 0)
        self.port_address_inputs: list[QLineEdit] = []
        for i in range(_NUM_PORTS):
            inp = QLineEdit()
            inp.setPlaceholderText(f"D{100 + i * 2}")
            inp.setMaximumWidth(80)
            self.port_address_inputs.append(inp)
            grid.addWidget(inp, 0, 1 + i)

        self.save_port_btn = QPushButton(STRINGS["save_btn"])
        self.save_port_btn.setObjectName("save-btn")
        grid.addWidget(self.save_port_btn, 0, _NUM_PORTS + 1)

        # Row 1: Judgment verdicts (3 groups spanning 3 columns each)
        grid.addWidget(QLabel(STRINGS["judgment_label"]), 1, 0)
        self.verdict_labels: list[QLabel] = []
        for g in range(_NUM_GROUPS):
            label = QLabel("--")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setObjectName("verdict-pending")
            self.verdict_labels.append(label)
            col_start = 1 + g * _PORTS_PER_GROUP
            grid.addWidget(label, 1, col_start, 1, _PORTS_PER_GROUP)

        # Row 2: Judgment address inputs + Save button
        grid.addWidget(QLabel(STRINGS["judgment_address_label"]), 2, 0)
        self.judgment_address_inputs: list[QLineEdit] = []
        for g in range(_NUM_GROUPS):
            inp = QLineEdit()
            inp.setPlaceholderText(f"M{200 + g}")
            inp.setMaximumWidth(80)
            self.judgment_address_inputs.append(inp)
            col_start = 1 + g * _PORTS_PER_GROUP
            grid.addWidget(inp, 2, col_start, 1, _PORTS_PER_GROUP)

        self.save_judgment_btn = QPushButton(STRINGS["save_btn"])
        self.save_judgment_btn.setObjectName("save-btn")
        grid.addWidget(self.save_judgment_btn, 2, _NUM_PORTS + 1)

        main_layout.addLayout(grid)

    def _setup_status_bar(self) -> None:
        """Create status bar with PLC, N1700, and Excel indicators."""
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        self.plc_status = QLabel(STRINGS["status_plc_disconnected"])
        self.n1700_status = QLabel(STRINGS["status_n1700_unavailable"])
        self.excel_status = QLabel(STRINGS["status_excel_closed"])

        status_bar.addPermanentWidget(self.plc_status)
        status_bar.addPermanentWidget(self.n1700_status)
        status_bar.addPermanentWidget(self.excel_status)

    def _load_stylesheet(self) -> None:
        """Load the QSS stylesheet."""
        qss_path = Path(__file__).parent / "resources" / "styles.qss"
        if qss_path.exists():
            self.setStyleSheet(qss_path.read_text())

    def add_measurement_row(
        self,
        time_str: str,
        values: list[float],
    ) -> None:
        """Add a row of measurement values to the table.

        Args:
            time_str: Formatted timestamp string.
            values: List of 9 port values.
        """
        row = self.measurement_table.rowCount()
        self.measurement_table.insertRow(row)
        self.measurement_table.setItem(row, 0, QTableWidgetItem(time_str))
        for i, val in enumerate(values):
            self.measurement_table.setItem(row, 1 + i, QTableWidgetItem(f"{val:.4f}"))
        self.measurement_table.scrollToBottom()

    def update_verdicts(self, verdicts: list[str]) -> None:
        """Update the verdict labels with OK/NG status.

        Args:
            verdicts: List of 3 verdict strings ("OK" or "NG").
        """
        for i, verdict in enumerate(verdicts):
            if i < len(self.verdict_labels):
                self.verdict_labels[i].setText(verdict)
                if verdict == "OK":
                    self.verdict_labels[i].setObjectName("verdict-ok")
                elif verdict == "NG":
                    self.verdict_labels[i].setObjectName("verdict-ng")
                else:
                    self.verdict_labels[i].setObjectName("verdict-pending")
                # Force style refresh
                self.verdict_labels[i].style().unpolish(self.verdict_labels[i])
                self.verdict_labels[i].style().polish(self.verdict_labels[i])

    def wire_services(
        self,
        measurement_svc: MeasurementService,
        register_mgr: RegisterManager,
        plc: PLCClient,
        n1700: N1700Controller | None = None,
        report_output_dir: Path | None = None,
        excel_path: Path | None = None,
    ) -> None:
        """Connect UI signals to services after DI wiring.

        Args:
            measurement_svc: The measurement orchestrator service.
            register_mgr: The register configuration manager.
            plc: The PLC client (for reading back state).
            n1700: The N1700 controller (for status polling).
            report_output_dir: Directory for exported reports.
            excel_path: Path to the Excel input file (for status polling).
        """
        self._measurement_svc = measurement_svc
        self._register_mgr = register_mgr
        self._plc = plc
        self._n1700: Any = n1700
        self._report_output_dir = report_output_dir or Path("./reports")
        self._excel_path = excel_path

        # Barcode input -> measurement service
        self.barcode_input.returnPressed.connect(self._on_barcode_entered)
        self.barcode_reset_btn.clicked.connect(self._on_barcode_reset)

        # Export button
        self.export_btn.clicked.connect(self._on_export_clicked)

        # Measurement signals -> UI updates
        measurement_svc.measurement_complete.connect(self._on_measurement_complete)
        measurement_svc.measurement_failed.connect(self._on_measurement_failed)

        # Save buttons
        self.save_port_btn.clicked.connect(self._on_save_registers)
        self.save_judgment_btn.clicked.connect(self._on_save_registers)

        # Load existing register config into inputs
        existing = register_mgr.get()
        if existing is not None:
            self._load_register_config(existing)

        # Status bar polling (every 2 seconds)
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._poll_status)
        self._status_timer.start(2000)
        self._poll_status()  # Initial poll

    @Slot()
    def _on_barcode_entered(self) -> None:
        """Handle barcode scan (Enter key / \\n terminator)."""
        text = self.barcode_input.text().strip()
        if text and hasattr(self, "_measurement_svc"):
            self._measurement_svc.part_id = text
            self.barcode_input.setReadOnly(True)

    @Slot()
    def _on_barcode_reset(self) -> None:
        """Reset barcode input for a new scan."""
        self.barcode_input.setReadOnly(False)
        self.barcode_input.clear()
        self.barcode_input.setFocus()
        if hasattr(self, "_measurement_svc"):
            self._measurement_svc.part_id = ""

    @Slot()
    def _on_export_clicked(self) -> None:
        """Export measurement history to Excel report."""
        if not hasattr(self, "_measurement_svc"):
            return

        history = self._measurement_svc.history
        if not history:
            self.statusBar().showMessage(STRINGS["export_empty"], 3000)
            return

        try:
            from n1700_bridge.services.report_exporter import ReportExporter

            exporter = ReportExporter(self._report_output_dir)
            filepath = exporter.export(history)
            msg = STRINGS["export_success"].format(filepath.name)
            self.statusBar().showMessage(msg, 5000)
            logger.info("Report exported via UI: {}", filepath)
        except Exception as e:
            msg = STRINGS["export_error"].format(str(e))
            self.statusBar().showMessage(msg, 5000)
            logger.error("Report export failed: {}", e)

    @Slot(object)
    def _on_measurement_complete(self, measurement: object) -> None:
        """Handle successful measurement — update table and verdicts."""
        from n1700_bridge.core.models import Measurement

        if not isinstance(measurement, Measurement):
            return

        time_str = measurement.timestamp.strftime("%H:%M:%S")
        values = [r.value for r in measurement.readings]
        self.add_measurement_row(time_str, values)

        verdicts = [j.verdict.value for j in measurement.judgments]
        self.update_verdicts(verdicts)

    @Slot(str)
    def _on_measurement_failed(self, error_msg: str) -> None:
        """Show error toast on measurement failure with Vietnamese messages."""
        # Match known error types to Vietnamese messages
        if "N1700" in error_msg or "window" in error_msg.lower():
            display_msg = STRINGS["error_n1700_not_found"]
        elif "Excel" in error_msg or "excel" in error_msg.lower():
            display_msg = STRINGS["error_excel_closed"]
        else:
            display_msg = error_msg
        self.statusBar().showMessage(f"⚠ {display_msg}", 5000)

    @Slot()
    def _on_save_registers(self) -> None:
        """Save register addresses from UI inputs."""
        from n1700_bridge.config.models import RegisterConfig

        if not hasattr(self, "_register_mgr"):
            return

        port_addresses: dict[int, str] = {}
        for i, inp in enumerate(self.port_address_inputs, start=1):
            text = inp.text().strip()
            if text:
                port_addresses[i] = text

        judgment_addresses: dict[int, str] = {}
        for i, inp in enumerate(self.judgment_address_inputs, start=1):
            text = inp.text().strip()
            if text:
                judgment_addresses[i] = text

        config = RegisterConfig(
            port_addresses=port_addresses,
            judgment_addresses=judgment_addresses,
        )
        self._register_mgr.save(config)
        self.statusBar().showMessage(STRINGS["saved_toast"], 3000)

    def _load_register_config(self, config: RegisterConfig) -> None:
        """Populate UI inputs from existing register config."""
        for port, addr in config.port_addresses.items():
            idx = port - 1
            if 0 <= idx < len(self.port_address_inputs):
                self.port_address_inputs[idx].setText(addr)

        for group, addr in config.judgment_addresses.items():
            idx = group - 1
            if 0 <= idx < len(self.judgment_address_inputs):
                self.judgment_address_inputs[idx].setText(addr)

    @Slot()
    def _poll_status(self) -> None:
        """Poll adapter statuses and update status bar indicators."""
        # PLC status
        if hasattr(self, "_plc"):
            try:
                connected = self._plc.is_connected()
            except Exception:
                connected = False
            if connected:
                self.plc_status.setText(f"● {STRINGS['status_plc_connected']}")
                self.plc_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
            else:
                self.plc_status.setText(f"● {STRINGS['status_plc_disconnected']}")
                self.plc_status.setStyleSheet("color: #F44336; font-weight: bold;")

        # N1700 status
        if hasattr(self, "_n1700") and self._n1700 is not None:
            try:
                available = self._n1700.is_window_available()
            except Exception:
                available = False
            if available:
                self.n1700_status.setText(f"● {STRINGS['status_n1700_available']}")
                self.n1700_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
            else:
                self.n1700_status.setText(f"● {STRINGS['status_n1700_unavailable']}")
                self.n1700_status.setStyleSheet("color: #F44336; font-weight: bold;")

        # Excel status
        if hasattr(self, "_excel_path") and self._excel_path is not None:
            excel_open = self._excel_path.exists()
            if excel_open:
                self.excel_status.setText(f"● {STRINGS['status_excel_open']}")
                self.excel_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
            else:
                self.excel_status.setText(f"● {STRINGS['status_excel_closed']}")
                self.excel_status.setStyleSheet("color: #F44336; font-weight: bold;")
