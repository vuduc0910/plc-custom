"""Tests for ReportExporter service."""

from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from n1700_bridge.core.models import (
    JudgmentGroup,
    Measurement,
    PortReading,
    Threshold,
    Verdict,
)
from n1700_bridge.services.report_exporter import ReportExporter


def _make_measurement(
    part_id: str = "TEST001",
    base_value: float = 0.01,
    verdict: Verdict = Verdict.OK,
) -> Measurement:
    """Create a test measurement with 9 ports and 3 judgment groups."""
    readings = [
        PortReading(port=i, value=base_value * i) for i in range(1, 10)
    ]
    judgments = [
        JudgmentGroup(ports=(1, 2, 3), verdict=verdict),
        JudgmentGroup(ports=(4, 5, 6), verdict=verdict),
        JudgmentGroup(ports=(7, 8, 9), verdict=verdict),
    ]
    return Measurement(
        timestamp=datetime(2025, 1, 15, 10, 30, 0),
        part_id=part_id,
        readings=readings,
        judgments=judgments,
    )


class TestReportExporter:
    """Tests for ReportExporter."""

    def test_export_creates_file(self, tmp_path: Path) -> None:
        """Export should create an .xlsx file in the output directory."""
        exporter = ReportExporter(tmp_path)
        measurements = [_make_measurement()]

        result = exporter.export(measurements)

        assert result.exists()
        assert result.suffix == ".xlsx"
        assert result.parent == tmp_path

    def test_export_file_has_correct_headers(self, tmp_path: Path) -> None:
        """The exported file should have the expected column headers."""
        exporter = ReportExporter(tmp_path)
        measurements = [_make_measurement()]

        result = exporter.export(measurements)
        wb = load_workbook(result)
        ws = wb.active
        assert ws is not None

        headers = [ws.cell(row=1, column=i).value for i in range(1, 15)]
        expected = (
            ["Timestamp", "Part ID"]
            + [f"Port {i}" for i in range(1, 10)]
            + ["Group 1", "Group 2", "Group 3"]
        )
        assert headers == expected
        wb.close()

    def test_export_correct_row_count(self, tmp_path: Path) -> None:
        """Should have 1 header + N data rows."""
        exporter = ReportExporter(tmp_path)
        measurements = [_make_measurement(part_id=f"PART{i}") for i in range(10)]

        result = exporter.export(measurements)
        wb = load_workbook(result)
        ws = wb.active
        assert ws is not None

        # Header + 10 data rows
        assert ws.max_row == 11
        wb.close()

    def test_export_row_data(self, tmp_path: Path) -> None:
        """Data row should contain timestamp, part_id, 9 values, 3 verdicts."""
        exporter = ReportExporter(tmp_path)
        measurement = _make_measurement(part_id="ABC123", base_value=0.02)
        result = exporter.export([measurement])

        wb = load_workbook(result)
        ws = wb.active
        assert ws is not None

        # Row 2 = first data row
        assert ws.cell(row=2, column=1).value == "2025-01-15 10:30:00"
        assert ws.cell(row=2, column=2).value == "ABC123"

        # Port 1 = 0.02 * 1 = 0.02
        assert ws.cell(row=2, column=3).value == 0.02
        # Port 9 = 0.02 * 9 = 0.18
        assert ws.cell(row=2, column=11).value == 0.18

        # Verdicts
        assert ws.cell(row=2, column=12).value == "OK"
        assert ws.cell(row=2, column=13).value == "OK"
        assert ws.cell(row=2, column=14).value == "OK"
        wb.close()

    def test_export_ng_verdicts(self, tmp_path: Path) -> None:
        """NG verdicts should be written correctly."""
        exporter = ReportExporter(tmp_path)
        measurement = _make_measurement(verdict=Verdict.NG)
        result = exporter.export([measurement])

        wb = load_workbook(result)
        ws = wb.active
        assert ws is not None

        assert ws.cell(row=2, column=12).value == "NG"
        assert ws.cell(row=2, column=13).value == "NG"
        assert ws.cell(row=2, column=14).value == "NG"
        wb.close()

    def test_export_empty_list(self, tmp_path: Path) -> None:
        """Exporting empty list should create file with only headers."""
        exporter = ReportExporter(tmp_path)
        result = exporter.export([])

        wb = load_workbook(result)
        ws = wb.active
        assert ws is not None

        assert ws.max_row == 1  # Only header
        wb.close()

    def test_export_creates_output_dir(self, tmp_path: Path) -> None:
        """Should create output directory if it doesn't exist."""
        output_dir = tmp_path / "nested" / "reports"
        exporter = ReportExporter(output_dir)
        result = exporter.export([_make_measurement()])

        assert output_dir.exists()
        assert result.exists()
