from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QTimer
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

from .handlers import MainWindowHandlers
from .resources.strings_vi import STRINGS
from .widgets.judgment_panel import JudgmentPanel

if TYPE_CHECKING:
    from n1700_bridge.config.models import RegisterConfig
    from n1700_bridge.core.n1700 import N1700Controller
    from n1700_bridge.core.plc import PLCClient
    from n1700_bridge.services.measurement_service import MeasurementService
    from n1700_bridge.services.register_manager import RegisterManager

_NUM_PORTS = 9


class MainWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(STRINGS["window_title"])
        self.setMinimumSize(900, 500)
        self._handlers = MainWindowHandlers(self)

        self._setup_ui()
        self._setup_status_bar()
        self._load_stylesheet()

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        self._setup_top_bar(main_layout)
        self._setup_measurement_table(main_layout)
        self._setup_register_grid(main_layout)

        self.judgment_panel = JudgmentPanel()
        main_layout.addWidget(self.judgment_panel)

    def _setup_top_bar(self, layout: QVBoxLayout) -> None:
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
        layout.addLayout(top_bar)

    def _setup_measurement_table(self, layout: QVBoxLayout) -> None:
        self.measurement_table = QTableWidget(0, _NUM_PORTS + 2)
        headers = [STRINGS["time_column"], STRINGS["part_id_column"]] + [
            str(i) for i in range(1, _NUM_PORTS + 1)
        ]
        self.measurement_table.setHorizontalHeaderLabels(headers)
        self.measurement_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.measurement_table.setMinimumHeight(150)
        layout.addWidget(self.measurement_table)

    def _setup_register_grid(self, layout: QVBoxLayout) -> None:
        grid = QGridLayout()

        grid.addWidget(QLabel(STRINGS["register_address_label"]), 0, 0)
        self.port_address_inputs: list[QLineEdit] = []
        for i in range(_NUM_PORTS):
            inp = QLineEdit()
            inp.setPlaceholderText(f"D{100 + i * 2}")
            inp.setMaximumWidth(80)
            self.port_address_inputs.append(inp)
            grid.addWidget(inp, 0, 1 + i)

        grid.addWidget(QLabel(STRINGS["zero_label"]), 1, 0)
        self.zero_inputs: list[QLineEdit] = []
        for i in range(_NUM_PORTS):
            inp = QLineEdit("0")
            inp.setMaximumWidth(80)
            self.zero_inputs.append(inp)
            grid.addWidget(inp, 1, 1 + i)

        self.save_port_btn = QPushButton(STRINGS["save_btn"])
        self.save_port_btn.setObjectName("save-btn")
        grid.addWidget(self.save_port_btn, 1, _NUM_PORTS + 1)

        layout.addLayout(grid)

    def _setup_status_bar(self) -> None:
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        self.plc_status = QLabel(STRINGS["status_plc_disconnected"])
        self.n1700_status = QLabel(STRINGS["status_n1700_unavailable"])
        self.excel_status = QLabel(STRINGS["status_excel_closed"])

        status_bar.addPermanentWidget(self.plc_status)
        status_bar.addPermanentWidget(self.n1700_status)
        status_bar.addPermanentWidget(self.excel_status)

    def _load_stylesheet(self) -> None:
        qss_path = Path(__file__).parent / "resources" / "styles.qss"
        if qss_path.exists():
            self.setStyleSheet(qss_path.read_text())

    def add_measurement_row(
        self, time_str: str, part_id: str, values: list[float],
    ) -> None:
        row = self.measurement_table.rowCount()
        self.measurement_table.insertRow(row)
        self.measurement_table.setItem(row, 0, QTableWidgetItem(time_str))
        self.measurement_table.setItem(row, 1, QTableWidgetItem(part_id))
        for i, val in enumerate(values):
            self.measurement_table.setItem(
                row, 2 + i, QTableWidgetItem(f"{val:.4f}"),
            )
        self.measurement_table.scrollToBottom()

    def wire_services(
        self,
        measurement_svc: MeasurementService,
        register_mgr: RegisterManager,
        plc: PLCClient,
        n1700: N1700Controller | None = None,
        report_output_dir: Path | None = None,
        excel_path: Path | None = None,
    ) -> None:
        self._measurement_svc = measurement_svc
        self._register_mgr = register_mgr
        self._plc = plc
        self._n1700: Any = n1700
        self._report_output_dir = report_output_dir or Path("./reports")
        self._excel_path = excel_path

        h = self._handlers
        self.barcode_input.returnPressed.connect(h.on_barcode_entered)
        self.barcode_reset_btn.clicked.connect(h.on_barcode_reset)
        self.export_btn.clicked.connect(h.on_export_clicked)
        measurement_svc.measurement_complete.connect(h.on_measurement_complete)
        measurement_svc.measurement_failed.connect(h.on_measurement_failed)
        self.manual_trigger_btn.clicked.connect(h.on_manual_trigger)
        self.save_port_btn.clicked.connect(h.on_save_registers)
        self.judgment_panel.save_judgment_btn.clicked.connect(h.on_save_registers)

        existing = register_mgr.get()
        if existing is not None:
            self._load_register_config(existing)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(h.poll_status)
        self._status_timer.start(2000)
        h.poll_status()

    def _on_barcode_reset(self) -> None:
        self._handlers.on_barcode_reset()

    def _load_register_config(self, config: RegisterConfig) -> None:
        for port, addr in config.port_addresses.items():
            idx = port - 1
            if 0 <= idx < len(self.port_address_inputs):
                self.port_address_inputs[idx].setText(addr)

        for port, value in config.zeros.items():
            idx = port - 1
            if 0 <= idx < len(self.zero_inputs):
                self.zero_inputs[idx].setText(str(value))

        self.judgment_panel.multiplier_input.setText(str(config.multiplier))

        for group, addr in config.judgment_addresses.items():
            idx = group - 1
            if 0 <= idx < len(self.judgment_panel.judgment_address_inputs):
                self.judgment_panel.judgment_address_inputs[idx].setText(addr)

        panel_config = {
            "judgment_groups": config.judgment_groups,
            "template_path": config.template_path,
            "template_input_cells": config.template_input_cells,
        }
        self.judgment_panel.load_from_config(panel_config)
