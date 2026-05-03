"""Measurement service — orchestrates the full measurement cycle."""

import time
from datetime import datetime

from loguru import logger
from PySide6.QtCore import QObject, Signal, Slot

from n1700_bridge.config.models import RegisterConfig
from n1700_bridge.core.excel_source import ExcelDataSource, ExcelSourceError
from n1700_bridge.core.models import Measurement, Verdict
from n1700_bridge.core.n1700 import N1700Controller, N1700Error
from n1700_bridge.core.plc import PLCClient, PLCError
from n1700_bridge.services.judgment_service import JudgmentService
from n1700_bridge.services.measurement_store import MeasurementStore
from n1700_bridge.services.register_manager import RegisterManager


class MeasurementService(QObject):
    """Orchestrates the full measurement cycle.

    Runs in a worker thread. Triggered by PLCListener.trigger_received.
    Steps:
        1. Click N1700 Data button
        2. Wait settling delay
        3. Read latest Excel row
        4. Compute OK/NG judgments
        5. Write values + judgments to PLC registers
        6. Emit measurement_complete
    """

    measurement_started = Signal()
    measurement_complete = Signal(object)  # Measurement
    measurement_failed = Signal(str)  # error message

    def __init__(
        self,
        plc: PLCClient,
        n1700: N1700Controller,
        excel: ExcelDataSource,
        judgment: JudgmentService,
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

    def restore_history(self, measurements: list[Measurement]) -> None:
        """Pre-populate in-memory history (e.g. from SQLite on startup)."""
        self._history = list(measurements)[-1000:]
        logger.info(
            "MeasurementService restored {} measurements into history",
            len(self._history),
        )

    @property
    def part_id(self) -> str:
        """Current part ID from barcode scan."""
        return self._part_id

    @part_id.setter
    def part_id(self, value: str) -> None:
        self._part_id = value
        logger.bind(part_id=value).info("Part ID set to: {}", value)

        # Gửi tín hiệu barcode_ready cho PLC
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
        """In-memory measurement history (max 1000 items)."""
        return list(self._history)

    @Slot()
    def run_cycle(self) -> None:
        """Execute a full measurement cycle.

        Called from worker thread after PLCListener detects trigger.
        """
        self.measurement_started.emit()
        part_id = self._part_id
        log = logger.bind(part_id=part_id)
        log.info("Measurement cycle started")

        try:
            # 0. Reset control bits
            log.debug("Step 0: Resetting control bits")
            self._plc.write_bit(self._barcode_ready_bit, False)
            self._plc.write_bit(self._done_bit, False)

            # 1. Click N1700 Data button
            log.debug("Step 1: Clicking N1700 Data button")
            self._n1700.click_data_button()

            # 2. Wait settling delay
            log.debug("Step 2: Waiting {}ms settling delay", self._settling_delay_ms)
            time.sleep(self._settling_delay_ms / 1000.0)

            # 3. Read latest Excel row
            log.debug("Step 3: Reading latest Excel row")
            readings = self._excel.read_latest_row()

            # 4. Compute OK/NG judgments
            log.debug("Step 4: Computing judgments")
            judgments = self._judgment.judge(readings)

            # 5. Build measurement result
            measurement = Measurement(
                timestamp=datetime.now(),
                part_id=part_id,
                readings=readings,
                judgments=judgments,
            )

            # 6. Write values + judgments to PLC
            reg_config = self._registers.get()
            if reg_config is not None:
                log.debug("Step 5: Writing to PLC registers")
                self._write_to_plc(measurement, reg_config)
            else:
                log.warning("No register config set, skipping PLC write")

            # 6b. Set done_bit = ON (PLC biết data đã sẵn sàng)
            log.debug("Step 6: Setting done_bit {} = ON", self._done_bit)
            self._plc.write_bit(self._done_bit, True)

            # 6c. Reset trigger_bit = OFF
            log.debug("Step 6c: Resetting trigger_bit {} = OFF", self._trigger_bit)
            self._plc.write_bit(self._trigger_bit, False)

            # 7. Persist to SQLite (best-effort)
            if self._store is not None:
                try:
                    self._store.save(measurement)
                except Exception:
                    log.exception("Failed to persist measurement to SQLite")

            # 8. Store in history (max 1000)
            self._history.append(measurement)
            if len(self._history) > 1000:
                self._history = self._history[-1000:]

            # 8. Emit success
            log.info(
                "Measurement cycle complete: {} readings, {} judgments",
                len(readings),
                [j.verdict.value for j in judgments],
            )
            self.measurement_complete.emit(measurement)

        except N1700Error as e:
            log.error("N1700 error: {}", e)
            self.measurement_failed.emit(str(e))
        except ExcelSourceError as e:
            log.error("Excel error: {}", e)
            self.measurement_failed.emit(str(e))
        except PLCError as e:
            log.error("PLC error: {}", e)
            self.measurement_failed.emit(str(e))
        except Exception as e:
            log.exception("Unexpected error in measurement cycle")
            self.measurement_failed.emit(f"Unexpected error: {e}")

    def _write_to_plc(
        self,
        measurement: Measurement,
        reg_config: RegisterConfig,
    ) -> None:
        """Write measurement values and judgments to PLC registers."""

        # Write port values as INT16 (value * 10000 to preserve 4 decimal places)
        # TODO(client-Q6.1): Confirm value type (int/float) with client.
        for reading in measurement.readings:
            addr = reg_config.port_addresses.get(reading.port)
            if addr:
                int_val = int(reading.value * 10000)
                self._plc.write_word(addr, int_val)

        # Write judgment bits (OK=1, NG=0)
        for i, judgment in enumerate(measurement.judgments, start=1):
            addr = reg_config.judgment_addresses.get(i)
            if addr:
                self._plc.write_bit(addr, judgment.verdict == Verdict.OK)
