"""PLC trigger listener — polls trigger bit in a QThread."""

import time

from loguru import logger
from PySide6.QtCore import QObject, Signal, Slot

from n1700_bridge.core.plc import PLCClient, PLCError


class PLCListener(QObject):
    """Polls a PLC trigger bit for rising edge detection.

    Runs in a QThread. Emits trigger_received on rising edge (0->1).
    Also polls rescan_address for barcode reset signal from PLC.
    """

    trigger_received = Signal()
    rescan_received = Signal()
    connection_lost = Signal()

    def __init__(
        self,
        plc: PLCClient,
        trigger_address: str = "M100",
        rescan_address: str = "D1002",
        poll_ms: int = 100,
    ) -> None:
        super().__init__()
        self._plc = plc
        self._trigger_address = trigger_address
        self._rescan_address = rescan_address
        self._poll_ms = poll_ms
        self._running = False
        self._last_state = False
        self._last_rescan_state = False

    @Slot()
    def start_polling(self) -> None:
        """Start polling loop. Called when QThread starts."""
        logger.info(
            "PLCListener start_polling: trigger={}, rescan={}, interval={}ms",
            self._trigger_address,
            self._rescan_address,
            self._poll_ms,
        )
        self._running = True
        self._last_state = False
        self._last_rescan_state = False

        while self._running:
            try:
                current = self._plc.read_bit(self._trigger_address)

                if current and not self._last_state:
                    logger.info("PLCListener: trigger rising edge detected on {}",
                                self._trigger_address)
                    self.trigger_received.emit()

                self._last_state = current

                self._poll_rescan()

            except PLCError:
                logger.warning("PLCListener: connection lost")
                self.connection_lost.emit()
                self._last_state = False
                self._last_rescan_state = False

            time.sleep(self._poll_ms / 1000.0)

    def _poll_rescan(self) -> None:
        """Poll rescan register and emit on rising edge."""
        current = self._plc.read_bit(self._rescan_address)
        if current and not self._last_rescan_state:
            logger.info(
                "PLCListener: rescan signal detected on {}",
                self._rescan_address,
            )
            self._plc.write_bit(self._rescan_address, False)
            self.rescan_received.emit()
        self._last_rescan_state = current

    def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
        logger.info("PLCListener stopped")
