import time
from datetime import datetime

_WORD_MIN = -32768
_WORD_MAX = 65535

from loguru import logger
from PySide6.QtCore import QObject, Signal, Slot

from n1700_bridge.config.models import RegisterConfig
from n1700_bridge.config.settings import HMIControlSettings
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

    raw_values_read = Signal(object)

    zero_captured = Signal(object)
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
        hmi_control: HMIControlSettings | None = None,
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
        self._hmi_control = hmi_control
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
        """Synchronous read; runs on caller thread. Prefer ``capture_zero`` from UI."""
        return self._excel.read_latest_row()

    @Slot()
    def capture_zero(self) -> None:
        """Async-safe slot: read raw port values on the worker thread.

        Connected via QueuedConnection from the UI so the call cannot block
        the UI event loop, even if the data source holds a long-running lock
        (e.g. while ``run_cycle`` is in its settling-delay sleep).
        """
        try:
            readings = self._excel.read_latest_row()
            logger.info("capture_zero read {} ports", len(readings))
            self.zero_captured.emit(readings)
        except Exception as e:
            logger.exception("capture_zero failed")
            self.zero_failed.emit(str(e))

    def write_zeros_to_hmi(self, zeros: dict[int, float]) -> None:
        """Write zero values to PLC registers (D1400-D1416) for HMI display.

        Written as 2-register Double Word slots, matching the port value
        registers (D1200-D1216) so the HMI reads them consistently.
        """
        if self._hmi_control is None:
            return
        for port, value in zeros.items():
            addr = self._hmi_control.zero_display_addresses.get(str(port))
            if addr:
                self._plc.write_words(addr, _to_dwords(value * 100, addr))
        logger.info("Wrote {} zero values to PLC for HMI display", len(zeros))

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
        self._plc.write_bit(self._barcode_ready_bit, False)
        self._plc.write_bit(self._done_bit, False)

    def _trigger_n1700_read(self, log: logger) -> None:  # type: ignore[type-arg]
        self._n1700.click_data_button()
        time.sleep(self._settling_delay_ms / 1000.0)

    def _read_port_values(self, log: logger) -> list[PortReading]:  # type: ignore[type-arg]
        raw_readings = self._excel.read_latest_row()
        log.info(
            "N1700 raw: {}",
            {r.port: round(r.value, 4) for r in raw_readings},
        )
        self.raw_values_read.emit(raw_readings)
        reg_config = self._registers.get()
        multiplier = reg_config.multiplier if reg_config else 1.0
        zeros = reg_config.zeros if reg_config else {}
        masters = reg_config.masters if reg_config else {}
        master_ranges = reg_config.master_ranges if reg_config else [[1, 4], [5, 8], [9, 9]]
        calibrated = self._apply_calibration(raw_readings, zeros, multiplier, masters, master_ranges)
        log.info(
            "Calibrated: {}",
            {r.port: round(r.value, 4) for r in calibrated},
        )
        return calibrated

    def _evaluate_judgments(
        self, log: logger, readings: list[PortReading],
    ):
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
            self._write_to_plc(measurement, reg_config)
            log.info(
                "PLC write: ports={}, verdicts={}, judgments={}",
                {r.port: _to_word(r.value * 100, "") for r in measurement.readings},
                {pv.port: pv.verdict.value for pv in measurement.port_verdicts},
                [j.verdict.value for j in measurement.judgments],
            )
        else:
            log.warning("No register config set, skipping PLC write")

        self._plc.write_bit(self._done_bit, True)
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
                self._plc.write_words(addr, _to_dwords(reading.value * 100, addr))

        for pv in measurement.port_verdicts:
            addr = reg_config.port_verdict_addresses.get(pv.port)
            if addr:
                self._plc.write_word(addr, 1 if pv.verdict == Verdict.OK else 0)

        for i, judgment in enumerate(measurement.judgments, start=1):
            addr = reg_config.judgment_addresses.get(i)
            if addr:
                self._plc.write_word(addr, 1 if judgment.verdict == Verdict.OK else 0)

        if self._hmi_control is not None:
            self._write_stats_to_plc(measurement.readings)

    def _write_stats_to_plc(self, readings: list[PortReading]) -> None:
        """Write MIN/MAX/AVG stats for port groups to PLC for HMI display."""
        assert self._hmi_control is not None
        group_1_4 = [r.value for r in readings if 1 <= r.port <= 4]
        group_5_8 = [r.value for r in readings if 5 <= r.port <= 8]

        if group_1_4:
            addr = self._hmi_control.stats_1_4_min
            self._plc.write_words(addr, _to_dwords(min(group_1_4) * 100, addr))
            addr = self._hmi_control.stats_1_4_max
            self._plc.write_words(addr, _to_dwords(max(group_1_4) * 100, addr))
            addr = self._hmi_control.stats_1_4_avg
            self._plc.write_words(addr, _to_dwords((sum(group_1_4) / len(group_1_4)) * 100, addr))

        if group_5_8:
            addr = self._hmi_control.stats_5_8_min
            self._plc.write_words(addr, _to_dwords(min(group_5_8) * 100, addr))
            addr = self._hmi_control.stats_5_8_max
            self._plc.write_words(addr, _to_dwords(max(group_5_8) * 100, addr))
            addr = self._hmi_control.stats_5_8_avg
            self._plc.write_words(addr, _to_dwords((sum(group_5_8) / len(group_5_8)) * 100, addr))

    @staticmethod
    def _apply_calibration(
        readings: list[PortReading],
        zeros: dict[int, float],
        multiplier: float,
        masters: dict[int, float] | None = None,
        master_ranges: list[list[int]] | None = None,
    ) -> list[PortReading]:
        port_master: dict[int, float] = {}
        if masters and master_ranges:
            for idx, rng in enumerate(master_ranges, start=1):
                if len(rng) == 2:
                    master_val = masters.get(idx, 0.0)
                    for p in range(rng[0], rng[1] + 1):
                        port_master[p] = master_val
        return [
            PortReading(
                port=r.port,
                value=(
                    (r.value - zeros.get(r.port, 0.0)) * multiplier
                    + port_master.get(r.port, 0.0)
                ),
            )
            for r in readings
        ]


def _to_word(raw: float, addr: str) -> int:
    """Clamp a raw float to 16-bit range for PLC WORD write.

    Accepts -32768..65535 (covers both signed and unsigned WORD).
    Values > 32767 are converted to signed representation for write_sign_word.
    """
    val = round(raw)
    if val < _WORD_MIN or val > _WORD_MAX:
        clamped = max(_WORD_MIN, min(_WORD_MAX, val))
        logger.warning(
            "16-bit overflow at {}: {} clamped to {}", addr, val, clamped,
        )
        return clamped
    return val


_SWORD_MIN = -32768
_SWORD_MAX = 32767


def _to_dwords(raw: float, addr: str) -> list[int]:
    """Convert a scaled float to a [low, high] signed-word pair for a 2-register slot.

    The measurement value (×100) fits in a signed 16-bit word; the high word is
    a sign extension (0 for positive, -1 for negative). Writing both registers
    keeps the slot consistent whether the HMI reads it as a 16-bit Word or as a
    32-bit Double Word — avoiding stale data in the neighbouring register.
    """
    val = round(raw)
    if val < _SWORD_MIN or val > _SWORD_MAX:
        clamped = max(_SWORD_MIN, min(_SWORD_MAX, val))
        logger.warning(
            "16-bit overflow at {}: {} clamped to {}", addr, val, clamped,
        )
        val = clamped
    high = -1 if val < 0 else 0
    return [val, high]
