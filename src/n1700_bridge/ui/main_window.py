from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
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
_NUM_GROUPS = 3
_GROUP_SPANS = [(1, 4), (5, 4), (9, 1)]

_TIME_COL_WIDTH = 70
_PARTID_COL_WIDTH = 90
_LABEL_COL_MIN = _TIME_COL_WIDTH + _PARTID_COL_WIDTH


class MainWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(STRINGS["window_title"])
        self.setMinimumSize(1000, 560)
        self._handlers = MainWindowHandlers(self)
        self._warning_banner_layout: QVBoxLayout | None = None

        self._setup_ui()
        self._setup_status_bar()
        self._load_stylesheet()

    def show_connection_warnings(self, warnings: list[str]) -> None:
        if not warnings or self._warning_banner_layout is None:
            return
        for msg in warnings:
            banner = QFrame()
            banner.setObjectName("warning-banner")
            row = QHBoxLayout(banner)
            row.setContentsMargins(12, 6, 8, 6)
            lbl = QLabel(msg)
            lbl.setObjectName("warning-text")
            lbl.setWordWrap(True)
            row.addWidget(lbl, stretch=1)
            close_btn = QPushButton("x")
            close_btn.setFixedSize(20, 20)
            close_btn.setObjectName("warning-close")
            close_btn.clicked.connect(lambda _checked: QApplication.quit())
            row.addWidget(close_btn)
            self._warning_banner_layout.addWidget(banner)

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        self._warning_banner_layout = QVBoxLayout()
        self._warning_banner_layout.setContentsMargins(0, 0, 0, 0)
        self._warning_banner_layout.setSpacing(2)
        main_layout.addLayout(self._warning_banner_layout)

        self._setup_top_bar(main_layout)
        self._setup_content(main_layout)

        self.judgment_panel = JudgmentPanel()
        main_layout.addWidget(self.judgment_panel)

    def _setup_top_bar(self, layout: QVBoxLayout) -> None:
        top_bar = QHBoxLayout()
        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText(STRINGS["barcode_placeholder"])
        self.barcode_input.setMinimumWidth(250)
        self.barcode_reset_btn = QPushButton(STRINGS["barcode_reset_btn"])
        self.barcode_reset_btn.setObjectName("reset-btn")
        self.export_btn = QPushButton(STRINGS["export_btn"])
        self.export_btn.setObjectName("export-btn")
        top_bar.addWidget(QLabel(STRINGS["part_id_label"]))
        top_bar.addWidget(self.barcode_input)
        top_bar.addWidget(self.barcode_reset_btn)
        top_bar.addStretch()
        top_bar.addWidget(self.export_btn)
        layout.addLayout(top_bar)

    def _setup_content(self, layout: QVBoxLayout) -> None:
        grid = QGridLayout()
        grid.setColumnMinimumWidth(0, _LABEL_COL_MIN)
        grid.setColumnStretch(0, 0)
        for col in range(1, _NUM_PORTS + 1):
            grid.setColumnStretch(col, 1)
        grid.setColumnStretch(_NUM_PORTS + 1, 0)

        self._setup_table_row(grid)
        self._setup_raw_row(grid)
        self._setup_zero_row(grid)
        self._setup_master_row(grid)
        self._setup_port_verdict_row(grid)
        self._setup_group_judgment_rows(grid)

        layout.addLayout(grid)

    def _setup_table_row(self, grid: QGridLayout) -> None:
        self.measurement_table = QTableWidget(0, _NUM_PORTS + 2)
        headers = [STRINGS["time_column"], STRINGS["part_id_column"]] + [
            str(i) for i in range(1, _NUM_PORTS + 1)
        ]
        self.measurement_table.setHorizontalHeaderLabels(headers)

        header = self.measurement_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.measurement_table.setColumnWidth(0, _TIME_COL_WIDTH)
        self.measurement_table.setColumnWidth(1, _PARTID_COL_WIDTH)
        for col in range(2, _NUM_PORTS + 2):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)

        self.measurement_table.setMinimumHeight(150)
        grid.addWidget(self.measurement_table, 0, 0, 1, _NUM_PORTS + 1)

    def _setup_raw_row(self, grid: QGridLayout) -> None:
        grid.addWidget(QLabel(STRINGS["raw_label"]), 1, 0)
        self.raw_displays: list[QLineEdit] = []
        for i in range(_NUM_PORTS):
            inp = QLineEdit("--")
            inp.setReadOnly(True)
            self.raw_displays.append(inp)
            grid.addWidget(inp, 1, 1 + i)

    def _setup_zero_row(self, grid: QGridLayout) -> None:
        grid.addWidget(QLabel(STRINGS["zero_label"]), 2, 0)
        self.zero_inputs: list[QLineEdit] = []
        for i in range(_NUM_PORTS):
            inp = QLineEdit("0")
            self.zero_inputs.append(inp)
            grid.addWidget(inp, 2, 1 + i)

        btn_layout = QHBoxLayout()
        self.get_zero_btn = QPushButton(STRINGS["get_zero_btn"])
        self.get_zero_btn.setObjectName("get-zero-btn")
        btn_layout.addWidget(self.get_zero_btn)

        self.save_port_btn = QPushButton(STRINGS["save_btn"])
        self.save_port_btn.setObjectName("save-btn")
        btn_layout.addWidget(self.save_port_btn)

        grid.addLayout(btn_layout, 2, _NUM_PORTS + 1)

    def _setup_master_row(self, grid: QGridLayout) -> None:
        grid.addWidget(QLabel(STRINGS["master_label"]), 3, 0)
        self.master_inputs: list[QLineEdit] = []
        for g, (start_col, col_span) in enumerate(_GROUP_SPANS):
            inp = QLineEdit("0")
            inp.setPlaceholderText(f"M{g + 1}")
            self.master_inputs.append(inp)
            grid.addWidget(inp, 3, start_col, 1, col_span)

        master_btn_layout = QHBoxLayout()
        self.save_master_btn = QPushButton(STRINGS["save_btn"])
        self.save_master_btn.setObjectName("save-btn")
        master_btn_layout.addWidget(self.save_master_btn)
        grid.addLayout(master_btn_layout, 3, _NUM_PORTS + 1)

    def _setup_port_verdict_row(self, grid: QGridLayout) -> None:
        grid.addWidget(QLabel(STRINGS["judgment_label"]), 4, 0)
        self.port_verdict_labels: list[QLabel] = []
        for i in range(_NUM_PORTS):
            lbl = QLabel("--")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setObjectName("verdict-pending")
            self.port_verdict_labels.append(lbl)
            grid.addWidget(lbl, 4, 1 + i)

    def _setup_group_judgment_rows(self, grid: QGridLayout) -> None:
        grid.addWidget(QLabel("Groups"), 5, 0)
        self.group_verdict_labels: list[QLabel] = []
        for g, (start_col, col_span) in enumerate(_GROUP_SPANS):
            name_lbl = QLabel(f"N{g + 1}")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(name_lbl, 5, start_col, 1, col_span)

            verdict_lbl = QLabel("--")
            verdict_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            verdict_lbl.setObjectName("verdict-pending")
            verdict_lbl.setMinimumHeight(32)
            self.group_verdict_labels.append(verdict_lbl)
            grid.addWidget(verdict_lbl, 6, start_col, 1, col_span)

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

        self.judgment_panel.verdict_labels = self.group_verdict_labels

        h = self._handlers
        self.barcode_input.returnPressed.connect(h.on_barcode_entered)
        self.barcode_reset_btn.clicked.connect(h.on_barcode_reset)
        self.export_btn.clicked.connect(h.on_export_clicked)
        measurement_svc.measurement_complete.connect(h.on_measurement_complete)
        measurement_svc.measurement_failed.connect(h.on_measurement_failed)
        measurement_svc.raw_values_read.connect(h.on_raw_values_read)
        measurement_svc.zero_captured.connect(h.on_zero_captured)
        measurement_svc.zero_failed.connect(h.on_zero_failed)
        self.get_zero_btn.clicked.connect(h.on_get_zero)
        self.save_port_btn.clicked.connect(h.on_save_registers)
        self.save_master_btn.clicked.connect(h.on_save_registers)
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
        for port, value in config.zeros.items():
            idx = port - 1
            if 0 <= idx < len(self.zero_inputs):
                self.zero_inputs[idx].setText(str(value))
        for group, value in config.masters.items():
            idx = group - 1
            if 0 <= idx < len(self.master_inputs):
                self.master_inputs[idx].setText(str(value))
        self.judgment_panel.multiplier_input.setText(str(config.multiplier))
        self.judgment_panel.load_from_config({
            "judgment_groups": config.judgment_groups,
            "template_path": config.template_path,
            "template_input_cells": config.template_input_cells,
        })
