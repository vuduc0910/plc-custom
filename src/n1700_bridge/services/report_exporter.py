from datetime import datetime
from pathlib import Path

from loguru import logger
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from n1700_bridge.core.models import Measurement, Verdict

_HEADER_FONT = Font(bold=True, color="FFFFFF")
_HEADER_FILL = PatternFill(start_color="1976D2", end_color="1976D2", fill_type="solid")
_HEADER_ALIGN = Alignment(horizontal="center")
_OK_FILL = PatternFill(start_color="4CAF50", end_color="4CAF50", fill_type="solid")
_NG_FILL = PatternFill(start_color="F44336", end_color="F44336", fill_type="solid")
_VERDICT_FONT = Font(bold=True, color="FFFFFF")

_NUM_PORTS = 9
_NUM_GROUPS = 3
_DECIMALS = 2
_NUMBER_FORMAT = "0.00"

# Column layout:
#   1: Timestamp, 2: Part ID
#   3 + (i-1)*2: Port i value,  4 + (i-1)*2: Port i Verdict   (i = 1..9)
#   2 + _NUM_PORTS*2 + 1 = 21: group section start
#   Group g (0-indexed): cell=21+g*3, value=22+g*3, verdict=23+g*3
_PORT_VALUE_COL = lambda i: 2 + (i - 1) * 2 + 1   # noqa: E731
_PORT_VERDICT_COL = lambda i: 2 + (i - 1) * 2 + 2  # noqa: E731
_GROUP_START_COL = 2 + _NUM_PORTS * 2 + 1           # = 21


class ReportExporter:

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir

    def export(self, measurements: list[Measurement]) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        filepath = self._output_dir / f"{timestamp}.xlsx"

        wb = Workbook()
        ws = wb.active
        if ws is None:
            ws = wb.create_sheet("Report")
        else:
            ws.title = "Report"

        headers = self._build_headers()
        ws.append(headers)
        self._style_header_row(ws, len(headers))

        for m in measurements:
            ws.append(self._build_data_row(m, len(headers)))

        self._style_verdict_cells(ws, len(measurements))
        self._style_numeric_cells(ws, len(measurements))
        self._auto_fit_columns(ws, headers, len(measurements))

        wb.save(filepath)
        wb.close()

        logger.info("Report exported: {} ({} measurements)", filepath, len(measurements))
        return filepath

    @staticmethod
    def _build_headers() -> list[str]:
        return (
            ["Timestamp", "Part ID"]
            + [
                item
                for i in range(1, _NUM_PORTS + 1)
                for item in (f"Port {i}", f"Port {i} Verdict")
            ]
            + [
                item
                for i in range(1, _NUM_GROUPS + 1)
                for item in (f"G{i} Cell", f"G{i} Value", f"G{i} Verdict")
            ]
        )

    @staticmethod
    def _build_data_row(m: Measurement, header_count: int) -> list[str | float]:
        row_data: list[str | float] = [
            m.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            m.part_id,
        ]

        readings_map = {r.port: r.value for r in m.readings}
        verdicts_map = {pv.port: pv.verdict.value for pv in m.port_verdicts}
        for port in range(1, _NUM_PORTS + 1):
            row_data.append(round(readings_map.get(port, 0.0), _DECIMALS))
            row_data.append(verdicts_map.get(port, ""))

        for j in m.judgments:
            row_data.append(j.output_cell)
            row_data.append(round(j.computed_value, _DECIMALS))
            row_data.append(j.verdict.value)

        while len(row_data) < header_count:
            row_data.append("")

        return row_data

    @staticmethod
    def _style_header_row(ws: object, col_count: int) -> None:
        for col_idx in range(1, col_count + 1):
            cell = ws.cell(row=1, column=col_idx)  # type: ignore[union-attr]
            cell.font = _HEADER_FONT
            cell.fill = _HEADER_FILL
            cell.alignment = _HEADER_ALIGN

    @staticmethod
    def _style_numeric_cells(ws: object, row_count: int) -> None:
        """Force two-decimal display on port value and group-value columns."""
        value_cols = [_PORT_VALUE_COL(i) for i in range(1, _NUM_PORTS + 1)]
        for g in range(_NUM_GROUPS):
            value_cols.append(_GROUP_START_COL + g * 3 + 1)

        for row_idx in range(2, row_count + 2):
            for col in value_cols:
                cell = ws.cell(row=row_idx, column=col)  # type: ignore[union-attr]
                if isinstance(cell.value, (int, float)):
                    cell.number_format = _NUMBER_FORMAT

    @staticmethod
    def _style_verdict_cells(ws: object, row_count: int) -> None:
        port_verdict_cols = [_PORT_VERDICT_COL(i) for i in range(1, _NUM_PORTS + 1)]
        group_verdict_cols = [_GROUP_START_COL + g * 3 + 2 for g in range(_NUM_GROUPS)]

        for row_idx in range(2, row_count + 2):
            for col in port_verdict_cols + group_verdict_cols:
                cell = ws.cell(row=row_idx, column=col)  # type: ignore[union-attr]
                if cell.value == Verdict.OK.value:
                    cell.fill = _OK_FILL
                    cell.font = _VERDICT_FONT
                elif cell.value == Verdict.NG.value:
                    cell.fill = _NG_FILL
                    cell.font = _VERDICT_FONT
                cell.alignment = _HEADER_ALIGN

    @staticmethod
    def _auto_fit_columns(ws: object, headers: list[str], row_count: int) -> None:
        for col_idx in range(1, len(headers) + 1):
            max_width = len(str(headers[col_idx - 1]))
            for row_idx in range(2, min(row_count + 2, 52)):
                val = ws.cell(row=row_idx, column=col_idx).value  # type: ignore[union-attr]
                if val is not None:
                    max_width = max(max_width, len(str(val)))
            col_letter = ws.cell(row=1, column=col_idx).column_letter  # type: ignore[union-attr]
            ws.column_dimensions[col_letter].width = max_width + 2  # type: ignore[union-attr]
