from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from n1700_bridge.ui.resources.strings_vi import STRINGS

if TYPE_CHECKING:
    pass

_NUM_GROUPS = 3


class JudgmentPanel(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.verdict_labels: list[QLabel] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._setup_template_section(layout)
        self._setup_multiplier_row(layout)

    def _setup_template_section(self, parent_layout: QVBoxLayout) -> None:
        row = QHBoxLayout()

        row.addWidget(QLabel(STRINGS["template_label"]))
        self.template_path_input = QLineEdit()
        self.template_path_input.setPlaceholderText("./config/template.xlsx")
        self.template_path_input.setMinimumWidth(250)
        row.addWidget(self.template_path_input)

        self.template_browse_btn = QPushButton(STRINGS["template_browse_btn"])
        self.template_browse_btn.clicked.connect(self._on_browse_template)
        row.addWidget(self.template_browse_btn)

        row.addWidget(QLabel(STRINGS["template_sheet_label"]))
        self.template_sheet_input = QLineEdit("Sheet1")
        self.template_sheet_input.setMaximumWidth(100)
        row.addWidget(self.template_sheet_input)

        row.addWidget(QLabel(STRINGS["template_input_label"]))
        self.template_input_cells_input = QLineEdit("B2:B10")
        self.template_input_cells_input.setMinimumWidth(120)
        row.addWidget(self.template_input_cells_input)

        row.addStretch()
        parent_layout.addLayout(row)

    def _setup_multiplier_row(self, parent_layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.addWidget(QLabel(STRINGS["multiplier_label"]))
        self.multiplier_input = QLineEdit("1")
        self.multiplier_input.setMaximumWidth(150)
        row.addWidget(self.multiplier_input)

        self.save_judgment_btn = QPushButton(STRINGS["save_btn"])
        self.save_judgment_btn.setObjectName("save-btn")
        row.addWidget(self.save_judgment_btn)

        row.addStretch()
        parent_layout.addLayout(row)

    def _on_browse_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            STRINGS["template_browse_btn"],
            "",
            "Excel Files (*.xlsx *.xls)",
        )
        if path:
            self.template_path_input.setText(path)

    def get_template_input_cells(self) -> list[str]:
        raw = self.template_input_cells_input.text().strip()
        return parse_cell_range(raw)

    def update_verdicts(self, judgments: list) -> None:
        from n1700_bridge.core.models import JudgmentGroup

        for i, jdg in enumerate(judgments):
            if not isinstance(jdg, JudgmentGroup):
                continue
            if i >= len(self.verdict_labels):
                break

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

    def load_from_config(self, config: dict) -> None:
        template = config.get("template_path")
        if template:
            self.template_path_input.setText(str(template))

        input_cells = config.get("template_input_cells")
        if input_cells:
            self.template_input_cells_input.setText(
                collapse_cell_range(input_cells)
            )


def parse_cell_range(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw:
        return []

    if ":" in raw:
        parts = raw.split(":")
        if len(parts) == 2:
            return _expand_range(parts[0].strip(), parts[1].strip())

    return [c.strip() for c in raw.split(",") if c.strip()]


def collapse_cell_range(cells: list[str]) -> str:
    if not cells:
        return ""
    if len(cells) == 1:
        return cells[0]
    return f"{cells[0]}:{cells[-1]}"


def _expand_range(start: str, end: str) -> list[str]:
    col_start = "".join(c for c in start if c.isalpha())
    row_start_str = "".join(c for c in start if c.isdigit())
    col_end = "".join(c for c in end if c.isalpha())
    row_end_str = "".join(c for c in end if c.isdigit())

    if col_start != col_end or not row_start_str or not row_end_str:
        return [start, end]

    row_start = int(row_start_str)
    row_end = int(row_end_str)
    return [f"{col_start}{r}" for r in range(row_start, row_end + 1)]
