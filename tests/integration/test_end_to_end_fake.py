"""Integration test — full measurement flow with all fake adapters."""

from pathlib import Path

import pytest

from n1700_bridge.adapters.excel_xlwings import OpenpyxlExcelSource
from n1700_bridge.adapters.n1700_fake import FakeN1700Controller
from n1700_bridge.adapters.plc_fake import FakePLCClient
from n1700_bridge.config.models import RegisterConfig
from n1700_bridge.core.models import Measurement, Threshold, Verdict
from n1700_bridge.services.judgment_service import JudgmentService
from n1700_bridge.services.measurement_service import MeasurementService
from n1700_bridge.services.register_manager import RegisterManager


@pytest.fixture()
def excel_path(tmp_path: Path) -> Path:
    """Create a temporary Excel file path."""
    return tmp_path / "test_output.xlsx"


@pytest.fixture()
def plc() -> FakePLCClient:
    """Create a connected FakePLCClient."""
    client = FakePLCClient()
    client.connect()
    return client


@pytest.fixture()
def n1700(excel_path: Path) -> FakeN1700Controller:
    """Create a FakeN1700Controller."""
    return FakeN1700Controller(excel_path)


@pytest.fixture()
def excel_source(excel_path: Path) -> OpenpyxlExcelSource:
    """Create an OpenpyxlExcelSource."""
    return OpenpyxlExcelSource(path=excel_path)


@pytest.fixture()
def register_mgr() -> RegisterManager:
    """Create a RegisterManager with default addresses."""
    mgr = RegisterManager()
    config = RegisterConfig(
        port_addresses={i: f"D{100 + (i - 1) * 2}" for i in range(1, 10)},
        judgment_addresses={1: "M200", 2: "M201", 3: "M202"},
    )
    mgr.save(config)
    return mgr


@pytest.fixture()
def thresholds() -> list[Threshold]:
    """Create default thresholds for all 9 ports."""
    return [Threshold(port=i, lower=-0.05, upper=0.05) for i in range(1, 10)]


@pytest.fixture()
def judgment_svc(thresholds: list[Threshold]) -> JudgmentService:
    """Create a JudgmentService with default 3-3-3 grouping."""
    return JudgmentService(thresholds, [(1, 2, 3), (4, 5, 6), (7, 8, 9)])


class TestEndToEndFake:
    """Full flow integration tests with fake adapters."""

    def test_single_measurement_cycle(
        self,
        plc: FakePLCClient,
        n1700: FakeN1700Controller,
        excel_source: OpenpyxlExcelSource,
        judgment_svc: JudgmentService,
        register_mgr: RegisterManager,
    ) -> None:
        """Fire trigger -> N1700 click -> read Excel -> judge -> write PLC."""
        svc = MeasurementService(
            plc=plc,  # type: ignore[arg-type]
            n1700=n1700,  # type: ignore[arg-type]
            excel=excel_source,  # type: ignore[arg-type]
            judgment=judgment_svc,
            registers=register_mgr,
            settling_delay_ms=0,  # No delay for tests
        )
        svc.part_id = "TEST-001"

        # Collect results via signal
        results: list[Measurement] = []
        errors: list[str] = []
        svc.measurement_complete.connect(lambda m: results.append(m))
        svc.measurement_failed.connect(lambda e: errors.append(e))

        # Run the cycle directly (not in QThread for test simplicity)
        svc.run_cycle()

        assert len(errors) == 0, f"Unexpected errors: {errors}"
        assert len(results) == 1

        measurement = results[0]
        assert measurement.part_id == "TEST-001"
        assert len(measurement.readings) == 9
        assert len(measurement.judgments) == 3

        # Verify PLC was written to
        words = plc.get_all_words()
        assert "D100" in words  # Port 1 value
        bits = plc.get_all_bits()
        # At least one judgment bit should be set
        assert any(addr in bits for addr in ["M200", "M201", "M202"])

    def test_multiple_cycles(
        self,
        plc: FakePLCClient,
        n1700: FakeN1700Controller,
        excel_source: OpenpyxlExcelSource,
        judgment_svc: JudgmentService,
        register_mgr: RegisterManager,
    ) -> None:
        """Run 5 measurement cycles without failure."""
        svc = MeasurementService(
            plc=plc,  # type: ignore[arg-type]
            n1700=n1700,  # type: ignore[arg-type]
            excel=excel_source,  # type: ignore[arg-type]
            judgment=judgment_svc,
            registers=register_mgr,
            settling_delay_ms=0,
        )
        svc.part_id = "MULTI-TEST"

        results: list[Measurement] = []
        errors: list[str] = []
        svc.measurement_complete.connect(lambda m: results.append(m))
        svc.measurement_failed.connect(lambda e: errors.append(e))

        for _ in range(5):
            svc.run_cycle()

        assert len(errors) == 0
        assert len(results) == 5
        assert len(svc.history) == 5

    def test_plc_values_written_correctly(
        self,
        plc: FakePLCClient,
        n1700: FakeN1700Controller,
        excel_source: OpenpyxlExcelSource,
        judgment_svc: JudgmentService,
        register_mgr: RegisterManager,
    ) -> None:
        """Verify PLC register values match measurement readings."""
        svc = MeasurementService(
            plc=plc,  # type: ignore[arg-type]
            n1700=n1700,  # type: ignore[arg-type]
            excel=excel_source,  # type: ignore[arg-type]
            judgment=judgment_svc,
            registers=register_mgr,
            settling_delay_ms=0,
        )
        svc.part_id = "PLC-TEST"

        results: list[Measurement] = []
        svc.measurement_complete.connect(lambda m: results.append(m))
        svc.run_cycle()

        assert len(results) == 1
        measurement = results[0]

        # Verify each port value was written
        words = plc.get_all_words()
        for reading in measurement.readings:
            addr = f"D{100 + (reading.port - 1) * 2}"
            expected = int(reading.value * 10000)
            assert words.get(addr) == expected, (
                f"Port {reading.port} at {addr}: "
                f"expected {expected}, got {words.get(addr)}"
            )

        # Verify judgment bits
        bits = plc.get_all_bits()
        for i, judgment in enumerate(measurement.judgments, start=1):
            addr = f"M{199 + i}"
            expected_bit = judgment.verdict == Verdict.OK
            assert bits.get(addr) == expected_bit

    def test_no_register_config_still_succeeds(
        self,
        plc: FakePLCClient,
        n1700: FakeN1700Controller,
        excel_source: OpenpyxlExcelSource,
        judgment_svc: JudgmentService,
    ) -> None:
        """Measurement succeeds even without register config (just no PLC write)."""
        empty_mgr = RegisterManager()
        svc = MeasurementService(
            plc=plc,  # type: ignore[arg-type]
            n1700=n1700,  # type: ignore[arg-type]
            excel=excel_source,  # type: ignore[arg-type]
            judgment=judgment_svc,
            registers=empty_mgr,
            settling_delay_ms=0,
        )
        svc.part_id = "NO-REG"

        results: list[Measurement] = []
        svc.measurement_complete.connect(lambda m: results.append(m))
        svc.run_cycle()

        assert len(results) == 1
