from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from PySide6.QtCore import QTimer, Slot
from PySide6.QtWidgets import QLabel

from n1700_bridge.ui.resources.strings_vi import STRINGS

if TYPE_CHECKING:
    from n1700_bridge.ui.main_window import MainWindow

_NUM_GROUPS = 3


class MainWindowHandlers:

    def __init__(self, window: MainWindow) -> None:
        self._w = window
        self._toast_label: QLabel | None = None

    def _show_toast(self, message: str, success: bool = True) -> None:
        if self._toast_label is not None:
            self._toast_label.deleteLater()

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
        QTimer.singleShot(3000, lbl.deleteLater)

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
    def on_manual_trigger(self) -> None:
        if not hasattr(self._w, "_measurement_svc"):
            return
        logger.info("Manual trigger fired from UI")
        self._w.statusBar().showMessage(STRINGS["manual_trigger_toast"], 2000)
        self._w._measurement_svc.run_cycle()

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

    @Slot()
    def on_get_zero(self) -> None:
        if not hasattr(self._w, "_measurement_svc"):
            return
        self._w.get_zero_btn.setEnabled(False)
        try:
            readings = self._w._measurement_svc.read_raw_values()
            for reading in readings:
                idx = reading.port - 1
                if 0 <= idx < len(self._w.zero_inputs):
                    self._w.zero_inputs[idx].setText(f"{reading.value:.4f}")
            self.on_save_registers()
            self._show_toast(STRINGS["get_zero_toast"])
        except Exception as exc:
            self._show_toast(
                STRINGS["get_zero_error"].format(str(exc)), success=False,
            )
        finally:
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
        input_cells = self._w.judgment_panel.get_template_input_cells()
        template_path = self._w.judgment_panel.template_path_input.text().strip()

        try:
            multiplier = float(self._w.judgment_panel.multiplier_input.text())
        except ValueError:
            multiplier = base.get("multiplier", 1.0)

        base.update({
            "multiplier": multiplier,
            "zeros": zeros,
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
        _poll_plc(self._w)
        _poll_n1700(self._w)
        _poll_excel(self._w)


def translate_error(error_msg: str) -> str:
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


def _poll_plc(w: MainWindow) -> None:
    if not hasattr(w, "_plc"):
        return
    try:
        connected = w._plc.is_connected()
    except Exception:
        connected = False
    if connected:
        w.plc_status.setText(f"● {STRINGS['status_plc_connected']}")
        w.plc_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
    else:
        w.plc_status.setText(f"● {STRINGS['status_plc_disconnected']}")
        w.plc_status.setStyleSheet("color: #F44336; font-weight: bold;")


def _poll_n1700(w: MainWindow) -> None:
    if not hasattr(w, "_n1700") or w._n1700 is None:
        return
    try:
        available = w._n1700.is_window_available()
    except Exception:
        available = False
    if available:
        w.n1700_status.setText(f"● {STRINGS['status_n1700_available']}")
        w.n1700_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
    else:
        w.n1700_status.setText(f"● {STRINGS['status_n1700_unavailable']}")
        w.n1700_status.setStyleSheet("color: #F44336; font-weight: bold;")


def _poll_excel(w: MainWindow) -> None:
    if not hasattr(w, "_excel_path") or w._excel_path is None:
        return
    if w._excel_path.exists():
        w.excel_status.setText(f"● {STRINGS['status_excel_open']}")
        w.excel_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
    else:
        w.excel_status.setText(f"● {STRINGS['status_excel_closed']}")
        w.excel_status.setStyleSheet("color: #F44336; font-weight: bold;")



def _collect_float_map(inputs: list) -> dict[int, float]:
    result: dict[int, float] = {}
    for i, inp in enumerate(inputs, start=1):
        text = inp.text().strip()
        if text:
            try:
                result[i] = float(text)
            except ValueError:
                pass
    return result


