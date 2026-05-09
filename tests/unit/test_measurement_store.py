from datetime import datetime
from pathlib import Path

import pytest

from n1700_bridge.core.models import (
    JudgmentGroup,
    Measurement,
    PortReading,
    Verdict,
)
from n1700_bridge.services.measurement_store import MeasurementStore


def _make_measurement(part_id: str = "P-001", offset: float = 0.0) -> Measurement:
    readings = [PortReading(port=i, value=0.01 * i + offset) for i in range(1, 10)]
    judgments = [
        JudgmentGroup(
            group_name="G1", output_cell="K2",
            computed_value=0.025, verdict=Verdict.OK,
        ),
        JudgmentGroup(
            group_name="G2", output_cell="L2",
            computed_value=0.15, verdict=Verdict.NG,
        ),
        JudgmentGroup(
            group_name="G3", output_cell="M2",
            computed_value=0.01, verdict=Verdict.OK,
        ),
    ]
    return Measurement(
        timestamp=datetime(2026, 5, 1, 10, 0, 0),
        part_id=part_id,
        readings=readings,
        judgments=judgments,
    )


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


class TestMeasurementStore:
    def test_creates_db_file_and_parent_dir(self, tmp_path: Path) -> None:
        nested = tmp_path / "nested" / "dir" / "test.db"
        store = MeasurementStore(nested)
        assert nested.exists()
        assert store.count() == 0

    def test_save_and_count(self, db_path: Path) -> None:
        store = MeasurementStore(db_path)
        store.save(_make_measurement("A"))
        store.save(_make_measurement("B"))
        assert store.count() == 2

    def test_save_returns_increasing_ids(self, db_path: Path) -> None:
        store = MeasurementStore(db_path)
        id1 = store.save(_make_measurement("A"))
        id2 = store.save(_make_measurement("B"))
        assert id2 > id1

    def test_load_recent_round_trip(self, db_path: Path) -> None:
        store = MeasurementStore(db_path)
        original = _make_measurement("RT-001")
        store.save(original)

        loaded = store.load_recent()
        assert len(loaded) == 1

        m = loaded[0]
        assert m.part_id == "RT-001"
        assert m.timestamp == original.timestamp
        assert len(m.readings) == 9
        assert m.readings[0].port == 1
        assert m.readings[0].value == pytest.approx(0.01)
        assert len(m.judgments) == 3
        assert m.judgments[0].group_name == "G1"
        assert m.judgments[0].output_cell == "K2"
        assert m.judgments[0].computed_value == pytest.approx(0.025)
        assert m.judgments[0].verdict == Verdict.OK
        assert m.judgments[1].verdict == Verdict.NG

    def test_load_recent_returns_oldest_first(self, db_path: Path) -> None:
        store = MeasurementStore(db_path)
        for i in range(5):
            store.save(_make_measurement(f"P-{i}", offset=i * 0.001))

        loaded = store.load_recent()
        assert [m.part_id for m in loaded] == ["P-0", "P-1", "P-2", "P-3", "P-4"]

    def test_load_recent_respects_limit(self, db_path: Path) -> None:
        store = MeasurementStore(db_path)
        for i in range(10):
            store.save(_make_measurement(f"P-{i}"))

        loaded = store.load_recent(limit=3)
        assert len(loaded) == 3
        assert [m.part_id for m in loaded] == ["P-7", "P-8", "P-9"]

    def test_persists_across_instances(self, db_path: Path) -> None:
        store1 = MeasurementStore(db_path)
        store1.save(_make_measurement("PERSIST"))

        store2 = MeasurementStore(db_path)
        assert store2.count() == 1
        loaded = store2.load_recent()
        assert loaded[0].part_id == "PERSIST"

    def test_empty_db_load_recent(self, db_path: Path) -> None:
        store = MeasurementStore(db_path)
        assert store.load_recent() == []
