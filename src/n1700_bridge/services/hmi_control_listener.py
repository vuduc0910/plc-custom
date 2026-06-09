"""HMI control listener — polls PLC for GET ZERO / MASTER SAVE signals from HMI."""

import time
from dataclasses import replace

from loguru import logger
from PySide6.QtCore import QMetaObject, QObject, Qt, Signal, Slot

from n1700_bridge.config.settings import HMIControlSettings
from n1700_bridge.core.plc import PLCClient, PLCError
from n1700_bridge.services.measurement_service import MeasurementService, _to_dwords
from n1700_bridge.services.register_manager import RegisterManager


class HMIControlListener(QObject):
    """Polls PLC for HMI control signals (GET ZERO, MASTER SAVE).

    Runs in a QThread. Detects rising edge on trigger bits and performs
    corresponding actions (capture zero, save master values).
    """

    zero_saved = Signal()
    master_saved = Signal()
    master_values_changed = Signal(object)
    zero_values_changed = Signal(object)
    connection_lost = Signal()

    def __init__(
        self,
        plc: PLCClient,
        measurement_svc: MeasurementService,
        register_mgr: RegisterManager,
        settings: HMIControlSettings,
    ) -> None:
        super().__init__()
        self._plc = plc
        self._measurement_svc = measurement_svc
        self._register_mgr = register_mgr
        self._settings = settings
        self._running = False
        self._pending_zeros: dict[int, float] | None = None
        self._last_get_zero = False
        self._last_save_zero = False
        self._last_save_master = False
        self._last_master_values: dict[int, float] | None = None
        self._last_zero_values: dict[int, float] | None = None

    @Slot()
    def start_polling(self) -> None:
        """Start polling loop. Called when QThread starts."""
        logger.info(
            "HMIControlListener start_polling: get_zero_trigger={}, "
            "get_zero_save={}, master_save={}, interval={}ms",
            self._settings.get_zero_trigger,
            self._settings.get_zero_save,
            self._settings.master_save,
            self._settings.poll_interval_ms,
        )
        self._running = True
        self._last_get_zero = False
        self._last_save_zero = False
        self._last_save_master = False
        self._last_master_values = None
        self._last_zero_values = None
        self._seed_zero_registers()

        while self._running:
            try:
                self._poll_get_zero_trigger()
                self._poll_save_zero()
                self._poll_save_master()
                self._poll_master_values()
                self._poll_zero_values()

            except PLCError:
                logger.warning("HMIControlListener: connection lost")
                self.connection_lost.emit()
                self._last_get_zero = False
                self._last_save_zero = False
                self._last_save_master = False

            time.sleep(self._settings.poll_interval_ms / 1000.0)

    def _poll_get_zero_trigger(self) -> None:
        """Poll D1220 (GET ZERO trigger) for rising edge."""
        current = self._plc.read_bit(self._settings.get_zero_trigger)
        if current and not self._last_get_zero:
            logger.info(
                "HMIControlListener: GET ZERO trigger detected on {}",
                self._settings.get_zero_trigger,
            )
            self._trigger_get_zero()
        self._last_get_zero = current

    def _poll_save_zero(self) -> None:
        """Poll M1220 (SAVE zero) for rising edge."""
        current = self._plc.read_bit(self._settings.get_zero_save)
        if current and not self._last_save_zero:
            logger.info(
                "HMIControlListener: SAVE ZERO signal detected on {}",
                self._settings.get_zero_save,
            )
            self._save_zeros()
        self._last_save_zero = current

    def _poll_save_master(self) -> None:
        """Poll M1230 (SAVE master) for rising edge."""
        current = self._plc.read_bit(self._settings.master_save)
        if current and not self._last_save_master:
            logger.info(
                "HMIControlListener: SAVE MASTER signal detected on {}",
                self._settings.master_save,
            )
            self._save_masters()
            # Auto-reset the save flag back to 0 after handling.
            self._plc.write_bit(self._settings.master_save, False)
        self._last_save_master = current

    def _poll_master_values(self) -> None:
        """Poll master registers (D1230/D1232/D1234) and emit on change.

        Lets the bridge UI mirror master values as the operator types them on
        the HMI, without waiting for SAVE. Emits only when a value actually
        changes so it does not overwrite manual edits on every poll cycle.
        """
        current = {
            1: self._plc.read_dword(self._settings.master_word_1_4) / 100.0,
            2: self._plc.read_dword(self._settings.master_word_5_8) / 100.0,
            3: self._plc.read_dword(self._settings.master_word_9) / 100.0,
        }
        if current != self._last_master_values:
            self._last_master_values = current
            self.master_values_changed.emit(dict(current))

    def _read_zero_values(self) -> dict[int, float]:
        """Read the per-port zero registers (D1400-D1416) as scaled floats."""
        values: dict[int, float] = {}
        for port_str, addr in self._settings.zero_display_addresses.items():
            values[int(port_str)] = self._plc.read_dword(addr) / 100.0
        return values

    def _poll_zero_values(self) -> None:
        """Poll the zero registers and emit on change.

        Lets the bridge UI mirror zero values as the operator types them on
        the HMI, mirroring ``_poll_master_values``. Emits only when a value
        actually changes so manual edits in the desktop UI are not clobbered
        on every poll cycle.
        """
        current = self._read_zero_values()
        if current != self._last_zero_values:
            self._last_zero_values = current
            self.zero_values_changed.emit(dict(current))

    def _seed_zero_registers(self) -> None:
        """Push persisted zeros to the HMI registers and seed the poll baseline.

        Without this the first poll would mirror whatever stale values the PLC
        retained into the UI, overwriting the zeros loaded from config. Writing
        the saved zeros first makes the HMI and the desktop start in sync.
        """
        config = self._register_mgr.get()
        zeros = dict(config.zeros) if config and config.zeros else {}
        if zeros:
            self._write_zeros_to_plc(zeros)
        self._last_zero_values = self._read_zero_values()

    def _trigger_get_zero(self) -> None:
        """Trigger zero capture on measurement service worker thread."""
        try:
            QMetaObject.invokeMethod(
                self._measurement_svc,
                "capture_zero",
                Qt.ConnectionType.QueuedConnection,
            )
            logger.debug("HMIControlListener: triggered capture_zero")
        except Exception as e:
            logger.error("HMIControlListener: failed to trigger capture_zero: {}", e)

    @Slot(object)
    def on_zero_captured(self, readings: object) -> None:
        """Receive zero readings from measurement service."""
        if not isinstance(readings, list):
            return
        self._pending_zeros = {r.port: r.value for r in readings}
        logger.info(
            "HMIControlListener: captured {} zero values, pending SAVE",
            len(self._pending_zeros),
        )
        # Show captured values on HMI (D1400-D1408) immediately so the operator
        # can review them before pressing SAVE (M1220).
        self._write_zeros_to_plc(self._pending_zeros)

    def _save_zeros(self) -> None:
        """Save the current zero values to RegisterConfig.

        Reads the live zero registers from the PLC (rather than only the last
        captured values) so zeros the operator typed directly on the HMI are
        persisted too, mirroring ``_save_masters``.
        """
        existing = self._register_mgr.get()
        if existing is None:
            logger.warning("HMIControlListener: no RegisterConfig to update")
            return

        try:
            zeros = self._read_zero_values()
        except PLCError as e:
            logger.error("HMIControlListener: failed to read zeros to save: {}", e)
            return

        new_config = replace(existing, zeros=zeros)
        self._register_mgr.save(new_config)
        self._last_zero_values = zeros
        self._pending_zeros = None
        self.zero_saved.emit()
        logger.info("HMIControlListener: zeros saved to RegisterConfig: {}", zeros)

    def _save_masters(self) -> None:
        """Read master values from PLC and save to RegisterConfig."""
        try:
            m1_raw = self._plc.read_dword(self._settings.master_word_1_4)
            m2_raw = self._plc.read_dword(self._settings.master_word_5_8)
            m3_raw = self._plc.read_dword(self._settings.master_word_9)

            m1 = m1_raw / 100.0
            m2 = m2_raw / 100.0
            m3 = m3_raw / 100.0

            logger.info(
                "HMIControlListener: read masters from PLC: "
                "{}={} ({}), {}={} ({}), {}={} ({})",
                self._settings.master_word_1_4, m1_raw, m1,
                self._settings.master_word_5_8, m2_raw, m2,
                self._settings.master_word_9, m3_raw, m3,
            )

            existing = self._register_mgr.get()
            if existing is None:
                logger.warning("HMIControlListener: no RegisterConfig to update")
                return

            new_masters = {1: m1, 2: m2, 3: m3}
            new_config = replace(existing, masters=new_masters)
            self._register_mgr.save(new_config)
            self.master_saved.emit()
            logger.info("HMIControlListener: masters saved to RegisterConfig")

        except Exception as e:
            logger.error("HMIControlListener: failed to save masters: {}", e)

    def _write_zeros_to_plc(self, zeros: dict[int, float]) -> None:
        """Write zero values to PLC registers (D1400-D1416) for HMI display.

        Written as 2-register Double Word slots, matching the port value
        registers (D1200-D1216) so the HMI reads them consistently.
        """
        for port, value in zeros.items():
            addr = self._settings.zero_display_addresses.get(str(port))
            if addr:
                self._plc.write_words(addr, _to_dwords(value * 100, addr))
        logger.info(
            "HMIControlListener: wrote {} zero values to PLC for HMI", len(zeros),
        )

    def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
        logger.info("HMIControlListener stopped")
