from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import xlwings as xw
from loguru import logger

from n1700_bridge.core.models import (
    ExcelTemplateConfig,
    JudgmentGroup,
    JudgmentGroupConfig,
    PortReading,
    PortVerdict,
    Verdict,
)

if TYPE_CHECKING:
    pass

_DECIMAL_PLACES = 6


class ExcelJudgmentError(Exception):
    pass


class JudgmentResult:

    def __init__(
        self,
        groups: list[JudgmentGroup],
        port_verdicts: list[PortVerdict],
    ) -> None:
        self.groups = groups
        self.port_verdicts = port_verdicts


class ExcelJudgmentService:

    def __init__(
        self,
        template_config: ExcelTemplateConfig,
        groups: list[JudgmentGroupConfig],
    ) -> None:
        self._template_config = template_config
        self._groups = groups
        self._app: xw.App | None = None
        self._wb: xw.Book | None = None
        self._sheet: xw.Sheet | None = None

    @property
    def groups(self) -> list[JudgmentGroupConfig]:
        return list(self._groups)

    def update_groups(self, groups: list[JudgmentGroupConfig]) -> None:
        self._groups = list(groups)
        logger.info("ExcelJudgmentService updated with {} groups", len(groups))

    def update_template(self, template_config: ExcelTemplateConfig) -> None:
        self.close()
        self._template_config = template_config
        logger.info("ExcelJudgmentService template updated: {}", template_config.path)

    def open(self) -> None:
        path = Path(self._template_config.path)
        if not path.exists():
            raise ExcelJudgmentError(f"Template not found: {path}")

        try:
            self._app = xw.App(visible=False)
            self._app.display_alerts = False
            self._app.screen_updating = False
            self._wb = self._app.books.open(str(path.resolve()))
            self._sheet = self._wb.sheets[self._template_config.sheet_name]
            logger.info("Excel template opened: {}", path)
        except Exception as e:
            self.close()
            raise ExcelJudgmentError(f"Failed to open template: {e}") from e

    def close(self) -> None:
        try:
            if self._wb is not None:
                self._wb.close()
            if self._app is not None:
                self._app.quit()
        except Exception:
            logger.warning("Error closing Excel template, ignoring")
        finally:
            self._wb = None
            self._app = None
            self._sheet = None

    def judge(self, readings: list[PortReading]) -> JudgmentResult:
        if self._sheet is None:
            self.open()
        assert self._sheet is not None

        try:
            return self._execute_judgment(readings)
        except Exception:
            logger.warning("COM error during judgment, reopening template")
            self.close()
            self.open()
            return self._execute_judgment(readings)

    def _execute_judgment(self, readings: list[PortReading]) -> JudgmentResult:
        self._write_inputs(readings)
        groups = self._read_group_verdicts()
        port_verdicts = self._read_port_verdicts()
        return JudgmentResult(groups=groups, port_verdicts=port_verdicts)

    def _write_inputs(self, readings: list[PortReading]) -> None:
        assert self._sheet is not None
        input_cells = self._template_config.input_cells

        written: dict[int, str] = {}
        for reading in readings:
            cell_index = reading.port - 1
            if 0 <= cell_index < len(input_cells):
                cell_addr = input_cells[cell_index]
                self._sheet.range(cell_addr).value = reading.value
                written[reading.port] = f"{cell_addr}={reading.value}"

        logger.info(
            "Judgment inputs written ({} ports): {}", len(written), written,
        )

    def _read_group_verdicts(self) -> list[JudgmentGroup]:
        assert self._sheet is not None
        results: list[JudgmentGroup] = []

        for group_cfg in self._groups:
            raw_value = self._sheet.range(group_cfg.output_cell).value
            computed = _safe_float(raw_value)
            verdict = Verdict.OK if computed == 1.0 else Verdict.NG

            results.append(JudgmentGroup(
                group_name=group_cfg.name,
                output_cell=group_cfg.output_cell,
                computed_value=computed,
                verdict=verdict,
            ))

            logger.info(
                "Judgment group '{}': cell {} raw={} computed={} -> {}",
                group_cfg.name,
                group_cfg.output_cell,
                raw_value,
                computed,
                verdict.value,
            )

        return results

    def _read_port_verdicts(self) -> list[PortVerdict]:
        assert self._sheet is not None
        verdict_cells = self._template_config.port_verdict_cells
        results: list[PortVerdict] = []

        for i, cell in enumerate(verdict_cells):
            raw = self._sheet.range(cell).value
            val = _safe_float(raw)
            verdict = Verdict.OK if val == 1.0 else Verdict.NG
            results.append(PortVerdict(port=i + 1, verdict=verdict))
            logger.info(
                "Judgment port {}: cell {} raw={} value={} -> {}",
                i + 1, cell, raw, val, verdict.value,
            )

        return results


def _safe_float(value: object) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
