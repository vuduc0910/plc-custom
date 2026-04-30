"""PLC trigger listener — polls trigger bit in a QThread."""

import time

from loguru import logger
from PySide6.QtCore import QObject, Signal, Slot

from n1700_bridge.core.plc import PLCClient, PLCError


class PLCListener(QObject):
    """Polls a PLC trigger bit for rising edge detection.

    Runs in a QThread. Emits trigger_received on rising edge (0->1).
    """

    trigger_received = Signal()
    connection_lost = Signal()

    def __init__(
        self,
        plc: PLCClient,
        trigger_address: str = "M100",
        poll_ms: int = 100,
    ) -> None:
        super().__init__()
        self._plc = plc
        self._trigger_address = trigger_address
        self._poll_ms = poll_ms
        self._running = False
        self._last_state = False

    @Slot()
    def start_polling(self) -> None:
        """Start polling loop. Called when QThread starts."""
        logger.info(
            "PLCListener start_polling: address={}, interval={}ms",
            self._trigger_address,
            self._poll_ms,
        )
        self._running = True
        self._last_state = False

        while self._running:
            try:
                current = self._plc.read_bit(self._trigger_address)

                # Rising edge detection: 0 -> 1
                if current and not self._last_state:
                    logger.info("PLCListener: trigger rising edge detected on {}",
                                self._trigger_address)
                    self.trigger_received.emit()

                self._last_state = current

            except PLCError:
                logger.warning("PLCListener: connection lost")
                self.connection_lost.emit()
                self._last_state = False

            time.sleep(self._poll_ms / 1000.0)

    def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
        logger.info("PLCListener stopped")
