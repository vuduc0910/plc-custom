"""Thread-safe register configuration manager with JSON persistence."""

import json
import threading
from pathlib import Path

from loguru import logger

from n1700_bridge.config.models import RegisterConfig


class RegisterManager:
    """Manages PLC register address configuration.

    Thread-safe via RLock. Persists to JSON file on save.
    Register addresses update live without restart (per spec slide 10).
    """

    def __init__(self, persist_path: Path | None = None) -> None:
        self._config: RegisterConfig | None = None
        self._lock = threading.RLock()
        self._persist_path = persist_path

    def save(self, config: RegisterConfig) -> None:
        """Save register configuration and persist to disk.

        Args:
            config: The register configuration to save.
        """
        with self._lock:
            self._config = config

        if self._persist_path is not None:
            self._persist_to_file(config)

        logger.info("RegisterManager saved config: {} port addresses, {} judgment addresses",
                     len(config.port_addresses), len(config.judgment_addresses))

    def get(self) -> RegisterConfig | None:
        """Get a snapshot of the current register configuration."""
        with self._lock:
            return self._config

    @classmethod
    def load_or_create(cls, persist_path: str | Path) -> "RegisterManager":
        """Load from JSON file if exists, otherwise create empty.

        Args:
            persist_path: Path to the JSON persistence file.

        Returns:
            A RegisterManager instance, loaded from file if available.
        """
        path = Path(persist_path)
        mgr = cls(persist_path=path)

        if path.exists():
            try:
                data = json.loads(path.read_text())
                config = RegisterConfig(
                    port_addresses={int(k): v for k, v in data.get("port_addresses", {}).items()},
                    judgment_addresses={
                        int(k): v for k, v in data.get("judgment_addresses", {}).items()
                    },
                    part_id_address=data.get("part_id_address"),
                )
                mgr._config = config
                logger.info("RegisterManager loaded config from {}", path)
            except Exception:
                logger.warning("Failed to load register config from {}, starting fresh", path)

        return mgr

    def _persist_to_file(self, config: RegisterConfig) -> None:
        """Write config to JSON file."""
        assert self._persist_path is not None
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "port_addresses": {str(k): v for k, v in config.port_addresses.items()},
                "judgment_addresses": {str(k): v for k, v in config.judgment_addresses.items()},
                "part_id_address": config.part_id_address,
            }
            self._persist_path.write_text(json.dumps(data, indent=2))
            logger.debug("RegisterManager persisted to {}", self._persist_path)
        except Exception:
            logger.exception("Failed to persist register config to {}", self._persist_path)
