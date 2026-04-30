"""Tests for RegisterManager."""

import json
from pathlib import Path

from n1700_bridge.config.models import RegisterConfig
from n1700_bridge.services.register_manager import RegisterManager


class TestRegisterManager:
    """Tests for RegisterManager save/load/persist."""

    def test_save_and_get(self) -> None:
        """Save config and retrieve it."""
        mgr = RegisterManager()
        config = RegisterConfig(
            port_addresses={1: "D100", 2: "D102"},
            judgment_addresses={1: "M200"},
        )
        mgr.save(config)
        result = mgr.get()

        assert result is not None
        assert result.port_addresses == {1: "D100", 2: "D102"}
        assert result.judgment_addresses == {1: "M200"}

    def test_get_returns_none_when_empty(self) -> None:
        """Get returns None before any save."""
        mgr = RegisterManager()
        assert mgr.get() is None

    def test_persist_to_file(self, tmp_path: Path) -> None:
        """Config is persisted to JSON file on save."""
        persist_file = tmp_path / "registers.json"
        mgr = RegisterManager(persist_path=persist_file)

        config = RegisterConfig(
            port_addresses={1: "D100", 2: "D102", 3: "D104"},
            judgment_addresses={1: "M200", 2: "M201", 3: "M202"},
        )
        mgr.save(config)

        assert persist_file.exists()
        data = json.loads(persist_file.read_text())
        assert data["port_addresses"]["1"] == "D100"
        assert data["judgment_addresses"]["3"] == "M202"

    def test_load_or_create_existing(self, tmp_path: Path) -> None:
        """Load from existing JSON file."""
        persist_file = tmp_path / "registers.json"
        persist_file.write_text(json.dumps({
            "port_addresses": {"1": "D200", "2": "D202"},
            "judgment_addresses": {"1": "M300"},
            "part_id_address": None,
        }))

        mgr = RegisterManager.load_or_create(persist_file)
        config = mgr.get()

        assert config is not None
        assert config.port_addresses == {1: "D200", 2: "D202"}
        assert config.judgment_addresses == {1: "M300"}

    def test_load_or_create_new(self, tmp_path: Path) -> None:
        """Create empty when file doesn't exist."""
        persist_file = tmp_path / "nonexistent.json"
        mgr = RegisterManager.load_or_create(persist_file)

        assert mgr.get() is None

    def test_overwrite_previous(self) -> None:
        """Saving new config replaces previous."""
        mgr = RegisterManager()
        mgr.save(RegisterConfig(port_addresses={1: "D100"}))
        mgr.save(RegisterConfig(port_addresses={1: "D200"}))

        result = mgr.get()
        assert result is not None
        assert result.port_addresses == {1: "D200"}

    def test_load_corrupted_file(self, tmp_path: Path) -> None:
        """Gracefully handle corrupted JSON file."""
        persist_file = tmp_path / "registers.json"
        persist_file.write_text("not valid json {{{")

        mgr = RegisterManager.load_or_create(persist_file)
        assert mgr.get() is None
