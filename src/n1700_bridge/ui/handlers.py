from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import TYPE_CHECKING

from loguru import logger
from PySide6.QtCore import QMetaObject, QObject, Qt, QTimer, Slot
from PySide6.QtWidgets import QDialog, QLabel

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

    @Slot(str)
    def on_barcode_changed(self, text: str) -> None:
        """Mirror the barcode field into ``part_id`` (and D1020) on every edit.

        Watches the input live so the PLC ready bit reflects whether the
        field currently holds a value — D1020 becomes 1 as soon as the field
        is non-empty and 0 when it is cleared — without waiting for Enter.
        """
        if not hasattr(self._w, "_measurement_svc"):
            return
        self._w._measurement_svc.part_id = text.strip()

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

        from n1700_bridge.ui.export_dialog import ExportRangeDialog

        timestamps = [m.timestamp for m in history]
        dialog = ExportRangeDialog(min(timestamps), max(timestamps), self._w)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        start, end = dialog.selected_range()
        # The picker exposes whole-second precision, so include the entire
        # end second regardless of sub-second timestamps on the records.
        upper = end + timedelta(seconds=1)
        selected = [m for m in history if start <= m.timestamp < upper]
        if not selected:
            self._show_toast(STRINGS["export_empty"], success=False)
            return

        try:
            from n1700_bridge.services.report_exporter import ReportExporter

            exporter = ReportExporter(self._w._report_output_dir)
            filepath = exporter.export(selected)
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
                self._w.raw_displays[idx].setText(f"{reading.value:.2f}")

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
                    self._w.zero_inputs[idx].setText(f"{reading.value:.3f}")
            self.on_save_registers()
            self._show_toast(STRINGS["get_zero_toast"])
            if hasattr(self._w, "_measurement_svc"):
                zeros = {r.port: r.value for r in readings}
                self._w._measurement_svc.write_zeros_to_hmi(zeros)
        finally:
            self._zero_capture_pending = False
            self._w.get_zero_btn.setEnabled(True)

    @Slot(object)
    def on_master_values_changed(self, values: object) -> None:
        """Live-update master fields when they change on the HMI."""
        if not isinstance(values, dict):
            return
        for group, value in values.items():
            idx = group - 1
            if 0 <= idx < len(self._w.master_inputs):
                self._w.master_inputs[idx].setText(f"{value:.2f}")

    @Slot(object)
    def on_zero_values_changed(self, values: object) -> None:
        """Live-update zero fields when they change on the HMI."""
        if not isinstance(values, dict):
            return
        for port, value in values.items():
            idx = port - 1
            if 0 <= idx < len(self._w.zero_inputs):
                self._w.zero_inputs[idx].setText(f"{value:.3f}")

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

        offsets = _collect_float_map(self._w.offset_inputs)
        zeros = _collect_float_map(self._w.zero_inputs)
        masters = _collect_float_map(self._w.master_inputs)
        input_cells = self._w.judgment_panel.get_template_input_cells()
        template_path = self._w.judgment_panel.template_path_input.text().strip()

        try:
            multiplier = float(self._w.judgment_panel.multiplier_input.text())
        except ValueError:
            multiplier = base.get("multiplier", 1.0)

        judgment_groups = base.get("judgment_groups", [])
        if hasattr(self._w, "_measurement_svc"):
            judgment_groups = [
                {"name": g.name, "output_cell": g.output_cell}
                for g in self._w._measurement_svc.judgment_service.groups
            ]

        base.update({
            "multiplier": multiplier,
            "offsets": offsets,
            "zeros": zeros,
            "masters": masters,
            "template_path": template_path or None,
            "template_input_cells": input_cells,
            "judgment_groups": judgment_groups,
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
        # Prefer output cells persisted in the DB config; fall back to whatever
        # the service was seeded with from settings.json on first run.
        saved_groups: list = []
        if hasattr(self._w, "_register_mgr"):
            cfg = self._w._register_mgr.get()
            if cfg is not None:
                saved_groups = cfg.judgment_groups
        groups: list[JudgmentGroupConfig] = []
        for i in range(_NUM_GROUPS):
            output_cell = ""
            if i < len(saved_groups) and isinstance(saved_groups[i], dict):
                output_cell = str(saved_groups[i].get("output_cell") or "")
            if not output_cell and i < len(existing_groups):
                output_cell = existing_groups[i].output_cell
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
            logger.info(
                "Judgment sync: template='{}' sheet='{}' input_cells={} groups={}",
                template_path, sheet_name, input_cells,
                [(g.name, g.output_cell) for g in groups],
            )
        else:
            logger.warning(
                "Judgment sync: no template path in UI/config — service keeps "
                "previous template; groups={}",
                [(g.name, g.output_cell) for g in groups],
            )

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
