"""HMI control listener — polls PLC for GET ZERO / MASTER SAVE signals from HMI."""

import time
from dataclasses import replace

from loguru import logger
from PySide6.QtCore import QMetaObject, QObject, Qt, Signal, Slot

from n1700_bridge.config.settings import HMIControlSettings
from n1700_bridge.core.plc import PLCClient, PLCError
from n1700_bridge.services.measurement_service import MeasurementService
from n1700_bridge.services.register_manager import RegisterManager


class HMIControlListener(QObject):
    """Polls PLC for HMI control signals (GET ZERO, MASTER SAVE).

    Runs in a QThread. Detects rising edge on trigger bits and performs
    corresponding actions (capture zero, save master values).
    """

    zero_saved = Signal()
    master_saved = Signal()
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

        while self._running:
            try:
                self._poll_get_zero_trigger()
                self._poll_save_zero()
                self._poll_save_master()

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
        self._last_save_master = current

    def _trigger_get_zero(self) -> None:
        """Trigger zero capture on measurement service worker thread."""
        try:
            QMetaObject.invokeMethod(
                self._measurement_svc,
                b"capture_zero",
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

    def _save_zeros(self) -> None:
        """Save pending zeros to RegisterConfig."""
        if self._pending_zeros is None:
            logger.warning("HMIControlListener: no pending zeros to save")
            return

        existing = self._register_mgr.get()
        if existing is None:
            logger.warning("HMIControlListener: no RegisterConfig to update")
            return

        new_config = replace(existing, zeros=dict(self._pending_zeros))
        self._register_mgr.save(new_config)
        self._pending_zeros = None
        self.zero_saved.emit()
        logger.info("HMIControlListener: zeros saved to RegisterConfig")

    def _save_masters(self) -> None:
        """Read master values from PLC and save to RegisterConfig."""
        try:
            m1_raw = self._plc.read_word(self._settings.master_word_1_4)
            m2_raw = self._plc.read_word(self._settings.master_word_5_8)
            m3_raw = self._plc.read_word(self._settings.master_word_9)

            m1 = m1_raw / 10000.0
            m2 = m2_raw / 10000.0
            m3 = m3_raw / 10000.0

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

    def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
        logger.info("HMIControlListener stopped")
