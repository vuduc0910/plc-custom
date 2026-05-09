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
    Verdict,
)

if TYPE_CHECKING:
    pass

_DECIMAL_PLACES = 6


class ExcelJudgmentError(Exception):
    pass


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

    def judge(self, readings: list[PortReading]) -> list[JudgmentGroup]:
        if self._sheet is None:
            self.open()
        assert self._sheet is not None

        self._write_inputs(readings)
        return self._read_outputs()

    def _write_inputs(self, readings: list[PortReading]) -> None:
        assert self._sheet is not None
        input_cells = self._template_config.input_cells

        for reading in readings:
            cell_index = reading.port - 1
            if 0 <= cell_index < len(input_cells):
                cell_addr = input_cells[cell_index]
                self._sheet.range(cell_addr).value = reading.value

        logger.debug("Wrote {} readings to template input cells", len(readings))

    def _read_outputs(self) -> list[JudgmentGroup]:
        assert self._sheet is not None
        results: list[JudgmentGroup] = []

        for group_cfg in self._groups:
            raw_value = self._sheet.range(group_cfg.output_cell).value
            computed = _safe_float(raw_value)
            is_ok = group_cfg.lower <= computed <= group_cfg.upper
            verdict = Verdict.OK if is_ok else Verdict.NG

            results.append(JudgmentGroup(
                group_name=group_cfg.name,
                output_cell=group_cfg.output_cell,
                computed_value=computed,
                verdict=verdict,
            ))

            logger.debug(
                "Group {} cell='{}' = {:.{prec}f} [{}, {}] -> {}",
                group_cfg.name,
                group_cfg.output_cell,
                computed,
                group_cfg.lower,
                group_cfg.upper,
                verdict.value,
                prec=_DECIMAL_PLACES,
            )

        return results


def _safe_float(value: object) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
