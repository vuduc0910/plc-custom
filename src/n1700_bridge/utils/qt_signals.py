"""SignalBus singleton for cross-component event communication."""

from PySide6.QtCore import QObject, Signal


class SignalBus(QObject):
    """Singleton signal bus for decoupled cross-component communication."""

    barcode_scanned = Signal(str)
    measurement_complete = Signal(object)  # Measurement
    measurement_failed = Signal(str)
    register_saved = Signal()
    status_update = Signal(str, bool)  # (component_name, is_connected)

    _instance: "SignalBus | None" = None

    @classmethod
    def instance(cls) -> "SignalBus":
        """Get or create the singleton SignalBus instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
