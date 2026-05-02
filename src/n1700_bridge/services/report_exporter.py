"""Report exporter — writes measurement history to Excel reports."""

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
_OK_FONT = Font(bold=True, color="FFFFFF")
_NG_FONT = Font(bold=True, color="FFFFFF")

_NUM_PORTS = 9
_NUM_GROUPS = 3


class ReportExporter:
    """Exports measurement history to .xlsx reports.

    Output filename format: YYYY-MM-DD_HHMMSS.xlsx
    Columns: Timestamp | PartID | Port1..Port9 | Group1..Group3
    """

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir

    def export(self, measurements: list[Measurement]) -> Path:
        """Export measurements to an Excel file.

        Args:
            measurements: List of measurement results to export.

        Returns:
            Path to the created report file.

        Raises:
            OSError: If the file cannot be written.
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        filename = f"{timestamp}.xlsx"
        filepath = self._output_dir / filename

        wb = Workbook()
        ws = wb.active
        if ws is None:
            ws = wb.create_sheet("Report")
        else:
            ws.title = "Report"

        # Write headers
        headers = (
            ["Timestamp", "Part ID"]
            + [f"Port {i}" for i in range(1, _NUM_PORTS + 1)]
            + [f"Group {i}" for i in range(1, _NUM_GROUPS + 1)]
        )
        ws.append(headers)

        # Style headers
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = _HEADER_FONT
            cell.fill = _HEADER_FILL
            cell.alignment = _HEADER_ALIGN

        # Write measurement rows
        for m in measurements:
            row_data: list[str | float] = [
                m.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                m.part_id,
            ]

            # Port readings (fill with 0.0 if missing)
            readings_map = {r.port: r.value for r in m.readings}
            for port in range(1, _NUM_PORTS + 1):
                row_data.append(readings_map.get(port, 0.0))

            # Judgment verdicts
            for j in m.judgments:
                row_data.append(j.verdict.value)

            # Pad if fewer than 3 judgments
            while len(row_data) < len(headers):
                row_data.append("")

            ws.append(row_data)

        # Style verdict cells (columns after Port9)
        verdict_start_col = 2 + _NUM_PORTS + 1  # 1-indexed
        for row_idx in range(2, len(measurements) + 2):
            for col_offset in range(_NUM_GROUPS):
                cell = ws.cell(row=row_idx, column=verdict_start_col + col_offset)
                if cell.value == Verdict.OK.value:
                    cell.fill = _OK_FILL
                    cell.font = _OK_FONT
                elif cell.value == Verdict.NG.value:
                    cell.fill = _NG_FILL
                    cell.font = _NG_FONT
                cell.alignment = _HEADER_ALIGN

        # Auto-fit column widths (approximate)
        for col_idx in range(1, len(headers) + 1):
            max_width = len(str(headers[col_idx - 1]))
            for row_idx in range(2, min(len(measurements) + 2, 52)):
                val = ws.cell(row=row_idx, column=col_idx).value
                if val is not None:
                    max_width = max(max_width, len(str(val)))
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = (
                max_width + 2
            )

        wb.save(filepath)
        wb.close()

        logger.info("Report exported: {} ({} measurements)", filepath, len(measurements))
        return filepath
