import time
from datetime import datetime

from loguru import logger
from PySide6.QtCore import QObject, Signal, Slot

from n1700_bridge.config.models import RegisterConfig
from n1700_bridge.core.excel_source import ExcelDataSource, ExcelSourceError
from n1700_bridge.core.models import (
    JudgmentGroupConfig,
    Measurement,
    PortReading,
    Verdict,
)
from n1700_bridge.core.n1700 import N1700Controller, N1700Error
from n1700_bridge.core.plc import PLCClient, PLCError
from n1700_bridge.services.excel_judgment_service import (
    ExcelJudgmentError,
    ExcelJudgmentService,
)
from n1700_bridge.services.measurement_store import MeasurementStore
from n1700_bridge.services.register_manager import RegisterManager


class MeasurementService(QObject):

    measurement_started = Signal()
    measurement_complete = Signal(object)
    measurement_failed = Signal(str)
    zero_captured = Signal(list)
    zero_failed = Signal(str)

    def __init__(
        self,
        plc: PLCClient,
        n1700: N1700Controller,
        excel: ExcelDataSource,
        judgment: ExcelJudgmentService,
        registers: RegisterManager,
        settling_delay_ms: int = 500,
        barcode_ready_bit: str = "M102",
        done_bit: str = "M101",
        trigger_bit: str = "M100",
        store: MeasurementStore | None = None,
    ) -> None:
        super().__init__()
        self._plc = plc
        self._n1700 = n1700
        self._excel = excel
        self._judgment = judgment
        self._registers = registers
        self._settling_delay_ms = settling_delay_ms
        self._barcode_ready_bit = barcode_ready_bit
        self._done_bit = done_bit
        self._trigger_bit = trigger_bit
        self._store = store
        self._part_id = ""
        self._history: list[Measurement] = []

    @property
    def judgment_service(self) -> ExcelJudgmentService:
        return self._judgment

    def update_judgment_groups(self, groups: list[JudgmentGroupConfig]) -> None:
        self._judgment.update_groups(groups)
        logger.info("Judgment groups updated: {} groups", len(groups))

    def restore_history(self, measurements: list[Measurement]) -> None:
        self._history = list(measurements)[-1000:]
        logger.info(
            "MeasurementService restored {} measurements into history",
            len(self._history),
        )

    @property
    def part_id(self) -> str:
        return self._part_id

    @part_id.setter
    def part_id(self, value: str) -> None:
        self._part_id = value
        logger.bind(part_id=value).info("Part ID set to: {}", value)

        if value:
            try:
                self._plc.write_bit(self._barcode_ready_bit, True)
                logger.bind(part_id=value).info(
                    "Barcode ready signal sent to PLC at {}", self._barcode_ready_bit
                )
            except PLCError as e:
                logger.bind(part_id=value).error(
                    "Failed to send barcode ready signal: {}", e
                )

    @property
    def history(self) -> list[Measurement]:
        return list(self._history)

    def read_raw_values(self) -> list[PortReading]:
        return self._excel.read_latest_row()

    @Slot()
    def capture_zero(self) -> None:
        try:
            readings = self._excel.read_latest_row()
            self.zero_captured.emit(readings)
        except Exception as exc:
            self.zero_failed.emit(str(exc))

    @Slot()
    def run_cycle(self) -> None:
        self.measurement_started.emit()
        part_id = self._part_id
        log = logger.bind(part_id=part_id)
        log.info("Measurement cycle started")

        try:
            self._reset_control_bits(log)
            self._trigger_n1700_read(log)
            readings = self._read_port_values(log)
            judgments = self._evaluate_judgments(log, readings)
            measurement = self._build_measurement(part_id, readings, judgments)
            self._write_results_to_plc(log, measurement)
            self._persist_measurement(log, measurement)
            self._emit_success(log, measurement)

        except (N1700Error, ExcelSourceError, PLCError, ExcelJudgmentError) as e:
            log.error("{} error: {}", type(e).__name__, e)
            self.measurement_failed.emit(str(e))
        except Exception as e:
            log.exception("Unexpected error in measurement cycle")
            self.measurement_failed.emit(f"Unexpected error: {e}")

    def _reset_control_bits(self, log: logger) -> None:  # type: ignore[type-arg]
        log.debug("Resetting control bits")
        self._plc.write_bit(self._barcode_ready_bit, False)
        self._plc.write_bit(self._done_bit, False)

    def _trigger_n1700_read(self, log: logger) -> None:  # type: ignore[type-arg]
        log.debug("Clicking N1700 Data button")
        self._n1700.click_data_button()
        log.debug("Waiting {}ms settling delay", self._settling_delay_ms)
        time.sleep(self._settling_delay_ms / 1000.0)

    def _read_port_values(self, log: logger) -> list[PortReading]:  # type: ignore[type-arg]
        log.debug("Reading latest Excel row")
        raw_readings = self._excel.read_latest_row()
        reg_config = self._registers.get()
        multiplier = reg_config.multiplier if reg_config else 1.0
        zeros = reg_config.zeros if reg_config else {}
        return self._apply_calibration(raw_readings, zeros, multiplier)

    def _evaluate_judgments(
        self, log: logger, readings: list[PortReading],
    ):
        log.debug("Computing judgments via Excel template")
        return self._judgment.judge(readings)

    @staticmethod
    def _build_measurement(
        part_id: str,
        readings: list[PortReading],
        result,
    ) -> Measurement:
        from n1700_bridge.services.excel_judgment_service import JudgmentResult
        groups = result.groups if isinstance(result, JudgmentResult) else []
        port_verdicts = result.port_verdicts if isinstance(result, JudgmentResult) else []
        return Measurement(
            timestamp=datetime.now(),
            part_id=part_id,
            readings=readings,
            judgments=groups,
            port_verdicts=port_verdicts,
        )

    def _write_results_to_plc(
        self, log: logger, measurement: Measurement,  # type: ignore[type-arg]
    ) -> None:
        reg_config = self._registers.get()
        if reg_config is not None:
            log.debug("Writing to PLC registers")
            self._write_to_plc(measurement, reg_config)
        else:
            log.warning("No register config set, skipping PLC write")

        log.debug("Setting done_bit {} = ON", self._done_bit)
        self._plc.write_bit(self._done_bit, True)
        log.debug("Resetting trigger_bit {} = OFF", self._trigger_bit)
        self._plc.write_bit(self._trigger_bit, False)

    def _persist_measurement(
        self, log: logger, measurement: Measurement,  # type: ignore[type-arg]
    ) -> None:
        if self._store is not None:
            try:
                self._store.save(measurement)
            except Exception:
                log.exception("Failed to persist measurement to SQLite")

        self._history.append(measurement)
        if len(self._history) > 1000:
            self._history = self._history[-1000:]

    def _emit_success(
        self, log: logger, measurement: Measurement,  # type: ignore[type-arg]
    ) -> None:
        log.info(
            "Measurement cycle complete: {} readings, {} judgments",
            len(measurement.readings),
            [j.verdict.value for j in measurement.judgments],
        )
        self.measurement_complete.emit(measurement)

    def _write_to_plc(
        self,
        measurement: Measurement,
        reg_config: RegisterConfig,
    ) -> None:
        for reading in measurement.readings:
            addr = reg_config.port_addresses.get(reading.port)
            if addr:
                int_val = int(reading.value * 10000)
                self._plc.write_word(addr, int_val)

        for pv in measurement.port_verdicts:
            addr = reg_config.port_verdict_addresses.get(pv.port)
            if addr:
                self._plc.write_word(addr, 1 if pv.verdict == Verdict.OK else 0)

        for i, judgment in enumerate(measurement.judgments, start=1):
            addr = reg_config.judgment_addresses.get(i)
            if addr:
                self._plc.write_word(addr, 1 if judgment.verdict == Verdict.OK else 0)

    @staticmethod
    def _apply_calibration(
        readings: list[PortReading],
        zeros: dict[int, float],
        multiplier: float,
    ) -> list[PortReading]:
        return [
            PortReading(
                port=r.port,
                value=(r.value - zeros.get(r.port, 0.0)) * multiplier,
            )
            for r in readings
        ]
