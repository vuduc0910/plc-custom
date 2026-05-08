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

_NUM_PORTS = 9
_NUM_GROUPS = 3


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

        self.manual_trigger_btn = QPushButton(STRINGS["manual_trigger_btn"])
        self.manual_trigger_btn.setObjectName("manual-trigger-btn")
        self.manual_trigger_btn.setStyleSheet(
            "QPushButton { background-color: #FF9800; color: white; "
            "font-weight: bold; padding: 6px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #F57C00; }"
            "QPushButton:pressed { background-color: #E65100; }"
        )

        self.export_btn = QPushButton(STRINGS["export_btn"])
        self.export_btn.setObjectName("export-btn")

        top_bar.addWidget(barcode_label)
        top_bar.addWidget(self.barcode_input)
        top_bar.addWidget(self.barcode_reset_btn)
        top_bar.addStretch()
        top_bar.addWidget(self.manual_trigger_btn)
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

        grid = QGridLayout()

        grid.addWidget(QLabel(STRINGS["register_address_label"]), 0, 0)
        self.port_address_inputs: list[QLineEdit] = []
        for i in range(_NUM_PORTS):
            inp = QLineEdit()
            inp.setPlaceholderText(f"D{100 + i * 2}")
            inp.setMaximumWidth(80)
            self.port_address_inputs.append(inp)
            grid.addWidget(inp, 0, 1 + i)

        grid.addWidget(QLabel(STRINGS["multiplier_label"]), 1, 0)
        self.multiplier_inputs: list[QLineEdit] = []
        for i in range(_NUM_PORTS):
            inp = QLineEdit("1")
            inp.setMaximumWidth(80)
            self.multiplier_inputs.append(inp)
            grid.addWidget(inp, 1, 1 + i)

        self.save_port_btn = QPushButton(STRINGS["save_btn"])
        self.save_port_btn.setObjectName("save-btn")
        grid.addWidget(self.save_port_btn, 1, _NUM_PORTS + 1)

        main_layout.addLayout(grid)

        formula_grid = QGridLayout()
        self.formula_inputs: list[QLineEdit] = []
        self.lower_inputs: list[QLineEdit] = []
        self.upper_inputs: list[QLineEdit] = []
        self.computed_labels: list[QLabel] = []
        self.verdict_labels: list[QLabel] = []
        self.judgment_address_inputs: list[QLineEdit] = []

        default_formulas = [
            "(p1+p2+p3+p4)/4",
            "(p5+p6+p7+p8)/4",
            "p9",
        ]

        headers = [
            "",
            STRINGS["formula_label"],
            STRINGS["lower_label"],
            STRINGS["upper_label"],
            STRINGS["computed_label"],
            STRINGS["judgment_label"],
            STRINGS["judgment_address_label"],
        ]
        for col, text in enumerate(headers):
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            formula_grid.addWidget(lbl, 0, col)

        for g in range(_NUM_GROUPS):
            row = g + 1
            formula_grid.addWidget(QLabel(f"N{g + 1}"), row, 0)

            formula_inp = QLineEdit(default_formulas[g])
            formula_inp.setMinimumWidth(180)
            self.formula_inputs.append(formula_inp)
            formula_grid.addWidget(formula_inp, row, 1)

            lower_inp = QLineEdit("-0.05")
            lower_inp.setMaximumWidth(80)
            self.lower_inputs.append(lower_inp)
            formula_grid.addWidget(lower_inp, row, 2)

            upper_inp = QLineEdit("0.05")
            upper_inp.setMaximumWidth(80)
            self.upper_inputs.append(upper_inp)
            formula_grid.addWidget(upper_inp, row, 3)

            computed_lbl = QLabel("--")
            computed_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            computed_lbl.setMinimumWidth(80)
            self.computed_labels.append(computed_lbl)
            formula_grid.addWidget(computed_lbl, row, 4)

            verdict_lbl = QLabel("--")
            verdict_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            verdict_lbl.setObjectName("verdict-pending")
            verdict_lbl.setMinimumWidth(60)
            self.verdict_labels.append(verdict_lbl)
            formula_grid.addWidget(verdict_lbl, row, 5)

            jdg_inp = QLineEdit()
            jdg_inp.setPlaceholderText(f"M{200 + g}")
            jdg_inp.setMaximumWidth(80)
            self.judgment_address_inputs.append(jdg_inp)
            formula_grid.addWidget(jdg_inp, row, 6)

        self.save_judgment_btn = QPushButton(STRINGS["save_btn"])
        self.save_judgment_btn.setObjectName("save-btn")
        formula_grid.addWidget(self.save_judgment_btn, _NUM_GROUPS + 1, 6)

        main_layout.addLayout(formula_grid)

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

    def update_verdicts(self, judgments: list[Any]) -> None:
        from n1700_bridge.core.models import JudgmentGroup

        for i, jdg in enumerate(judgments):
            if not isinstance(jdg, JudgmentGroup):
                continue
            if i >= len(self.verdict_labels):
                break

            self.computed_labels[i].setText(f"{jdg.computed_value:.6f}")

            verdict = jdg.verdict.value
            self.verdict_labels[i].setText(verdict)
            if verdict == "OK":
                self.verdict_labels[i].setObjectName("verdict-ok")
            elif verdict == "NG":
                self.verdict_labels[i].setObjectName("verdict-ng")
            else:
                self.verdict_labels[i].setObjectName("verdict-pending")
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

        # Manual trigger button
        self.manual_trigger_btn.clicked.connect(self._on_manual_trigger)

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
    def _on_manual_trigger(self) -> None:
        """Fire a manual measurement cycle (bypasses PLC trigger)."""
        if not hasattr(self, "_measurement_svc"):
            return
        logger.info("Manual trigger fired from UI")
        self.statusBar().showMessage(STRINGS["manual_trigger_toast"], 2000)
        self._measurement_svc.run_cycle()

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

        self.update_verdicts(measurement.judgments)

    @Slot(str)
    def _on_measurement_failed(self, error_msg: str) -> None:
        """Show error toast on measurement failure with Vietnamese messages."""
        display_msg = self._translate_error(error_msg)
        self.statusBar().showMessage(f"\u26a0 {display_msg}", 5000)

    @staticmethod
    def _translate_error(error_msg: str) -> str:
        msg_lower = error_msg.lower()
        if "dll not connected" in msg_lower:
            return STRINGS["error_dll_disconnected"]
        if "timeout" in msg_lower and "n1700" in msg_lower:
            return STRINGS["error_dll_timeout"]
        if "polldata" in msg_lower or "poll channel" in msg_lower:
            return STRINGS["error_dll_poll"]
        if "window" in msg_lower:
            return STRINGS["error_n1700_not_found"]
        if "n1700" in msg_lower:
            return STRINGS["error_dll_general"]
        if "excel" in msg_lower:
            return STRINGS["error_excel_closed"]
        return error_msg

    @Slot()
    def _on_save_registers(self) -> None:
        from n1700_bridge.config.models import RegisterConfig

        if not hasattr(self, "_register_mgr"):
            return

        port_addresses: dict[int, str] = {}
        for i, inp in enumerate(self.port_address_inputs, start=1):
            text = inp.text().strip()
            if text:
                port_addresses[i] = text

        multipliers: dict[int, float] = {}
        for i, inp in enumerate(self.multiplier_inputs, start=1):
            text = inp.text().strip()
            if text:
                try:
                    multipliers[i] = float(text)
                except ValueError:
                    pass

        judgment_addresses: dict[int, str] = {}
        for i, inp in enumerate(self.judgment_address_inputs, start=1):
            text = inp.text().strip()
            if text:
                judgment_addresses[i] = text

        formula_groups: list[dict[str, object]] = []
        for i in range(_NUM_GROUPS):
            formula_groups.append({
                "formula": self.formula_inputs[i].text().strip(),
                "lower": float(self.lower_inputs[i].text() or "0"),
                "upper": float(self.upper_inputs[i].text() or "0"),
            })

        config = RegisterConfig(
            port_addresses=port_addresses,
            multipliers=multipliers,
            judgment_addresses=judgment_addresses,
            formula_groups=formula_groups,
        )
        self._register_mgr.save(config)
        self._sync_judgment_from_ui()
        self.statusBar().showMessage(STRINGS["saved_toast"], 3000)

    def _sync_judgment_from_ui(self) -> None:
        from n1700_bridge.core.models import FormulaGroupConfig

        if not hasattr(self, "_measurement_svc"):
            return

        default_port_groups = [(1, 2, 3, 4), (5, 6, 7, 8), (9,)]
        groups: list[FormulaGroupConfig] = []
        for i in range(_NUM_GROUPS):
            formula = self.formula_inputs[i].text().strip()
            try:
                lower = float(self.lower_inputs[i].text())
            except ValueError:
                lower = 0.0
            try:
                upper = float(self.upper_inputs[i].text())
            except ValueError:
                upper = 0.0
            groups.append(FormulaGroupConfig(
                ports=default_port_groups[i],
                formula=formula,
                lower=lower,
                upper=upper,
            ))
        self._measurement_svc.update_judgment(groups)

    def _load_register_config(self, config: RegisterConfig) -> None:
        for port, addr in config.port_addresses.items():
            idx = port - 1
            if 0 <= idx < len(self.port_address_inputs):
                self.port_address_inputs[idx].setText(addr)

        for port, value in config.multipliers.items():
            idx = port - 1
            if 0 <= idx < len(self.multiplier_inputs):
                self.multiplier_inputs[idx].setText(str(value))

        for group, addr in config.judgment_addresses.items():
            idx = group - 1
            if 0 <= idx < len(self.judgment_address_inputs):
                self.judgment_address_inputs[idx].setText(addr)

        for i, fg in enumerate(config.formula_groups):
            if i >= _NUM_GROUPS:
                break
            if "formula" in fg:
                self.formula_inputs[i].setText(str(fg["formula"]))
            if "lower" in fg:
                self.lower_inputs[i].setText(str(fg["lower"]))
            if "upper" in fg:
                self.upper_inputs[i].setText(str(fg["upper"]))

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
