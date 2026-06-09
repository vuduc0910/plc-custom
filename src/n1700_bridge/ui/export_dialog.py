from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QWidget,
)

from n1700_bridge.ui.resources.strings_vi import STRINGS

_DT_FORMAT = "yyyy-MM-dd HH:mm:ss"


class ExportRangeDialog(QDialog):
    """Modal dialog letting the user pick a start/end time for the export.

    The two fields default to the time span of the available measurements so
    that accepting without changes exports everything.
    """

    def __init__(
        self,
        default_start: datetime,
        default_end: datetime,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(STRINGS["export_range_title"])

        self.start_edit = QDateTimeEdit(self)
        self.start_edit.setCalendarPopup(True)
        self.start_edit.setDisplayFormat(_DT_FORMAT)
        self.start_edit.setDateTime(QDateTime(default_start))

        self.end_edit = QDateTimeEdit(self)
        self.end_edit.setCalendarPopup(True)
        self.end_edit.setDisplayFormat(_DT_FORMAT)
        self.end_edit.setDateTime(QDateTime(default_end))

        form = QFormLayout(self)
        form.addRow(STRINGS["export_start_label"], self.start_edit)
        form.addRow(STRINGS["export_end_label"], self.end_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def selected_range(self) -> tuple[datetime, datetime]:
        """Return the chosen (start, end) datetimes, ordered start <= end."""
        start = self.start_edit.dateTime().toPython()
        end = self.end_edit.dateTime().toPython()
        if start > end:
            start, end = end, start
        return start, end
