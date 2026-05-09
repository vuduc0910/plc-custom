from pathlib import Path

import pytest

from n1700_bridge.adapters.excel_xlwings import OpenpyxlExcelSource
from n1700_bridge.adapters.n1700_fake import FakeN1700Controller
from n1700_bridge.adapters.plc_fake import FakePLCClient
from n1700_bridge.config.models import RegisterConfig
from n1700_bridge.core.models import (
    ExcelTemplateConfig,
    JudgmentGroup,
    JudgmentGroupConfig,
    Measurement,
    PortReading,
    Verdict,
)
from n1700_bridge.services.excel_judgment_service import ExcelJudgmentService
from n1700_bridge.services.measurement_service import MeasurementService
from n1700_bridge.services.register_manager import RegisterManager


class FakeExcelJudgmentService(ExcelJudgmentService):

    def __init__(self, groups: list[JudgmentGroupConfig]) -> None:
        template_config = ExcelTemplateConfig(
            path="fake.xlsx",
            sheet_name="Sheet1",
            input_cells=tuple(f"B{i}" for i in range(2, 11)),
        )
        super().__init__(template_config, groups)

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def judge(self, readings: list[PortReading]) -> list[JudgmentGroup]:
        readings_map = {r.port: r.value for r in readings}
        results: list[JudgmentGroup] = []
        for group_cfg in self._groups:
            computed = sum(
                readings_map.get(i, 0.0) for i in range(1, 10)
            ) / 9.0
            is_ok = group_cfg.lower <= computed <= group_cfg.upper
            verdict = Verdict.OK if is_ok else Verdict.NG
            results.append(JudgmentGroup(
                group_name=group_cfg.name,
                output_cell=group_cfg.output_cell,
                computed_value=computed,
                verdict=verdict,
            ))
        return results


@pytest.fixture()
def excel_path(tmp_path: Path) -> Path:
    return tmp_path / "test_output.xlsx"


@pytest.fixture()
def plc() -> FakePLCClient:
    client = FakePLCClient()
    client.connect()
    return client


@pytest.fixture()
def n1700(excel_path: Path) -> FakeN1700Controller:
    return FakeN1700Controller(excel_path)


@pytest.fixture()
def excel_source(excel_path: Path) -> OpenpyxlExcelSource:
    return OpenpyxlExcelSource(path=excel_path)


@pytest.fixture()
def register_mgr() -> RegisterManager:
    mgr = RegisterManager()
    config = RegisterConfig(
        port_addresses={i: f"D{100 + (i - 1) * 2}" for i in range(1, 10)},
        judgment_addresses={1: "M200", 2: "M201", 3: "M202"},
    )
    mgr.save(config)
    return mgr


DEFAULT_GROUPS = [
    JudgmentGroupConfig(name="G1", output_cell="K2", lower=-0.05, upper=0.05),
    JudgmentGroupConfig(name="G2", output_cell="L2", lower=-0.05, upper=0.05),
    JudgmentGroupConfig(name="G3", output_cell="M2", lower=-0.05, upper=0.05),
]


@pytest.fixture()
def judgment_svc() -> FakeExcelJudgmentService:
    return FakeExcelJudgmentService(DEFAULT_GROUPS)


class TestEndToEndFake:

    def test_single_measurement_cycle(
        self,
        plc: FakePLCClient,
        n1700: FakeN1700Controller,
        excel_source: OpenpyxlExcelSource,
        judgment_svc: FakeExcelJudgmentService,
        register_mgr: RegisterManager,
    ) -> None:
        svc = MeasurementService(
            plc=plc,
            n1700=n1700,
            excel=excel_source,
            judgment=judgment_svc,
            registers=register_mgr,
            settling_delay_ms=0,
        )
        svc.part_id = "TEST-001"

        results: list[Measurement] = []
        errors: list[str] = []
        svc.measurement_complete.connect(lambda m: results.append(m))
        svc.measurement_failed.connect(lambda e: errors.append(e))

        svc.run_cycle()

        assert len(errors) == 0, f"Unexpected errors: {errors}"
        assert len(results) == 1

        measurement = results[0]
        assert measurement.part_id == "TEST-001"
        assert len(measurement.readings) == 9
        assert len(measurement.judgments) == 3

        words = plc.get_all_words()
        assert "D100" in words
        bits = plc.get_all_bits()
        assert any(addr in bits for addr in ["M200", "M201", "M202"])

    def test_multiple_cycles(
        self,
        plc: FakePLCClient,
        n1700: FakeN1700Controller,
        excel_source: OpenpyxlExcelSource,
        judgment_svc: FakeExcelJudgmentService,
        register_mgr: RegisterManager,
    ) -> None:
        svc = MeasurementService(
            plc=plc,
            n1700=n1700,
            excel=excel_source,
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
        judgment_svc: FakeExcelJudgmentService,
        register_mgr: RegisterManager,
    ) -> None:
        svc = MeasurementService(
            plc=plc,
            n1700=n1700,
            excel=excel_source,
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

        words = plc.get_all_words()
        for reading in measurement.readings:
            addr = f"D{100 + (reading.port - 1) * 2}"
            expected = int(reading.value * 10000)
            assert words.get(addr) == expected, (
                f"Port {reading.port} at {addr}: "
                f"expected {expected}, got {words.get(addr)}"
            )

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
        judgment_svc: FakeExcelJudgmentService,
    ) -> None:
        empty_mgr = RegisterManager()
        svc = MeasurementService(
            plc=plc,
            n1700=n1700,
            excel=excel_source,
            judgment=judgment_svc,
            registers=empty_mgr,
            settling_delay_ms=0,
        )
        svc.part_id = "NO-REG"

        results: list[Measurement] = []
        svc.measurement_complete.connect(lambda m: results.append(m))
        svc.run_cycle()

        assert len(results) == 1
