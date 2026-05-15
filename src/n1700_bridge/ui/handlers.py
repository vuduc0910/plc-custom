from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from loguru import logger
from PySide6.QtCore import QMetaObject, QObject, Qt, QTimer, Slot
from PySide6.QtWidgets import QLabel

from n1700_bridge.ui.resources.strings_vi import STRINGS
from n1700_bridge.ui.status_polling import (
    poll_excel,
    poll_n1700,
    poll_plc,
    translate_error,
)

if TYPE_CHECKING:
    from n1700_bridge.ui.main_window import MainWindow

_NUM_GROUPS = 3


class MainWindowHandlers(QObject):

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self._w = window
        self._toast_label: QLabel | None = None
        self._zero_capture_pending = False

    def _show_toast(self, message: str, success: bool = True) -> None:
        try:
            if self._toast_label is not None:
                self._toast_label.hide()
                self._toast_label.deleteLater()
        except RuntimeError:
            pass
        self._toast_label = None

        color = "#4CAF50" if success else "#F44336"
        lbl = QLabel(message, self._w)
        lbl.setStyleSheet(
            f"background-color: {color}; color: white; padding: 8px 16px;"
            f" border-radius: 4px; font-weight: bold; font-size: 13px;"
        )
        lbl.adjustSize()
        lbl.move(
            (self._w.width() - lbl.width()) // 2,
            self._w.height() - lbl.height() - 40,
        )
        lbl.raise_()
        lbl.show()
        self._toast_label = lbl
        QTimer.singleShot(3000, self._dismiss_toast)

    def _dismiss_toast(self) -> None:
        try:
            if self._toast_label is not None:
                self._toast_label.deleteLater()
        except RuntimeError:
            pass
        self._toast_label = None

    @Slot()
    def on_barcode_entered(self) -> None:
        text = self._w.barcode_input.text().strip()
        if text and hasattr(self._w, "_measurement_svc"):
            self._w._measurement_svc.part_id = text
            self._w.barcode_input.setReadOnly(True)

    @Slot()
    def on_barcode_reset(self) -> None:
        self._w.barcode_input.setReadOnly(False)
        self._w.barcode_input.clear()
        self._w.barcode_input.setFocus()
        if hasattr(self._w, "_measurement_svc"):
            self._w._measurement_svc.part_id = ""

    @Slot()
    def on_export_clicked(self) -> None:
        if not hasattr(self._w, "_measurement_svc"):
            return

        history = self._w._measurement_svc.history
        if not history:
            self._show_toast(STRINGS["export_empty"], success=False)
            return

        try:
            from n1700_bridge.services.report_exporter import ReportExporter

            exporter = ReportExporter(self._w._report_output_dir)
            filepath = exporter.export(history)
            msg = STRINGS["export_success"].format(filepath.name)
            self._show_toast(msg)
            logger.info("Report exported via UI: {}", filepath)
        except Exception as e:
            msg = STRINGS["export_error"].format(str(e))
            self._show_toast(msg, success=False)
            logger.error("Report export failed: {}", e)

    @Slot(object)
    def on_measurement_complete(self, measurement: object) -> None:
        from n1700_bridge.core.models import Measurement

        if not isinstance(measurement, Measurement):
            return

        time_str = measurement.timestamp.strftime("%H:%M:%S")
        values = [r.value for r in measurement.readings]
        self._w.add_measurement_row(time_str, measurement.part_id, values)
        self._w.judgment_panel.update_verdicts(measurement.judgments)
        self._update_port_verdicts(measurement)

    @Slot(str)
    def on_measurement_failed(self, error_msg: str) -> None:
        display_msg = translate_error(error_msg)
        self._w.statusBar().showMessage(f"\u26a0 {display_msg}", 5000)

    @Slot(object)
    def on_raw_values_read(self, readings: object) -> None:
        if not isinstance(readings, list):
            return
        for reading in readings:
            idx = reading.port - 1
            if 0 <= idx < len(self._w.raw_displays):
                self._w.raw_displays[idx].setText(f"{reading.value:.4f}")

    @Slot()
    def on_get_zero(self) -> None:
        """Dispatch zero capture to the measurement worker thread.

        Using QueuedConnection guarantees the read cannot block the UI thread
        even if the data source holds a long-running lock during ``run_cycle``.
        Result arrives via ``on_zero_captured`` / ``on_zero_failed``.
        """
        if not hasattr(self._w, "_measurement_svc"):
            return
        if self._zero_capture_pending:
            return
        self._zero_capture_pending = True
        self._w.get_zero_btn.setEnabled(False)
        try:
            QMetaObject.invokeMethod(
                self._w._measurement_svc,
                "capture_zero",
                Qt.ConnectionType.QueuedConnection,
            )
        except Exception as exc:
            self._zero_capture_pending = False
            self._w.get_zero_btn.setEnabled(True)
            self._show_toast(
                STRINGS["get_zero_error"].format(str(exc)), success=False,
            )

    @Slot(object)
    def on_zero_captured(self, readings: object) -> None:
        try:
            if not isinstance(readings, list):
                return
            for reading in readings:
                idx = reading.port - 1
                if 0 <= idx < len(self._w.zero_inputs):
                    self._w.zero_inputs[idx].setText(f"{reading.value:.4f}")
            self.on_save_registers()
            self._show_toast(STRINGS["get_zero_toast"])
        finally:
            self._zero_capture_pending = False
            self._w.get_zero_btn.setEnabled(True)

    @Slot(str)
    def on_zero_failed(self, error_msg: str) -> None:
        self._show_toast(
            STRINGS["get_zero_error"].format(error_msg), success=False,
        )
        self._zero_capture_pending = False
        self._w.get_zero_btn.setEnabled(True)

    @Slot()
    def on_save_registers(self) -> None:
        from dataclasses import asdict

        from n1700_bridge.config.models import RegisterConfig

        if not hasattr(self._w, "_register_mgr"):
            return

        existing = self._w._register_mgr.get()
        base = asdict(existing) if existing else {}

        zeros = _collect_float_map(self._w.zero_inputs)
        masters = _collect_float_map(self._w.master_inputs)
        input_cells = self._w.judgment_panel.get_template_input_cells()
        template_path = self._w.judgment_panel.template_path_input.text().strip()

        try:
            multiplier = float(self._w.judgment_panel.multiplier_input.text())
        except ValueError:
            multiplier = base.get("multiplier", 1.0)

        base.update({
            "multiplier": multiplier,
            "zeros": zeros,
            "masters": masters,
            "template_path": template_path or None,
            "template_input_cells": input_cells,
        })
        config = RegisterConfig(**base)
        self._w._register_mgr.save(config)
        self._sync_judgment_from_ui()
        self._show_toast(STRINGS["saved_toast"])

    def _sync_judgment_from_ui(self) -> None:
        from n1700_bridge.core.models import ExcelTemplateConfig, JudgmentGroupConfig

        if not hasattr(self._w, "_measurement_svc"):
            return

        panel = self._w.judgment_panel
        existing_groups = self._w._measurement_svc.judgment_service.groups
        groups: list[JudgmentGroupConfig] = []
        for i in range(_NUM_GROUPS):
            output_cell = existing_groups[i].output_cell if i < len(existing_groups) else ""
            groups.append(JudgmentGroupConfig(
                name=f"G{i + 1}",
                output_cell=output_cell,
            ))
        self._w._measurement_svc.update_judgment_groups(groups)

        template_path = panel.template_path_input.text().strip()
        sheet_name = panel.template_sheet_input.text().strip() or "Sheet1"
        input_cells = panel.get_template_input_cells()
        if template_path:
            template_cfg = ExcelTemplateConfig(
                path=template_path,
                sheet_name=sheet_name,
                input_cells=tuple(input_cells),
            )
            self._w._measurement_svc.judgment_service.update_template(template_cfg)

    def _update_port_verdicts(self, measurement) -> None:
        from n1700_bridge.core.models import Measurement

        if not isinstance(measurement, Measurement):
            return
        for pv in measurement.port_verdicts:
            idx = pv.port - 1
            if 0 <= idx < len(self._w.port_verdict_labels):
                lbl = self._w.port_verdict_labels[idx]
                lbl.setText(pv.verdict.value)
                if pv.verdict.value == "OK":
                    lbl.setObjectName("verdict-ok")
                elif pv.verdict.value == "NG":
                    lbl.setObjectName("verdict-ng")
                else:
                    lbl.setObjectName("verdict-pending")
                lbl.style().unpolish(lbl)
                lbl.style().polish(lbl)

    @Slot()
    def poll_status(self) -> None:
        poll_plc(self._w)
        poll_n1700(self._w)
        poll_excel(self._w)


def _collect_float_map(inputs: list) -> dict[int, float]:
    result: dict[int, float] = {}
    for i, inp in enumerate(inputs, start=1):
        text = inp.text().strip()
        if text:
            with contextlib.suppress(ValueError):
                result[i] = float(text)
    return result
