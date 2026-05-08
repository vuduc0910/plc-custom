"""SQLite persistence for measurement history.

Persists every successful measurement cycle (timestamp, part_id, 9 port readings,
3 judgment groups) into a local SQLite database so history survives app restarts
and crashes.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from loguru import logger

from n1700_bridge.core.models import (
    JudgmentGroup,
    Measurement,
    PortReading,
    Verdict,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS measurements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    part_id     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS port_readings (
    measurement_id  INTEGER NOT NULL,
    port            INTEGER NOT NULL,
    value           REAL    NOT NULL,
    PRIMARY KEY (measurement_id, port),
    FOREIGN KEY (measurement_id) REFERENCES measurements(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS judgments (
    measurement_id  INTEGER NOT NULL,
    group_index     INTEGER NOT NULL,
    ports           TEXT    NOT NULL,
    formula         TEXT    NOT NULL DEFAULT '',
    computed_value  REAL    NOT NULL DEFAULT 0.0,
    verdict         TEXT    NOT NULL,
    PRIMARY KEY (measurement_id, group_index),
    FOREIGN KEY (measurement_id) REFERENCES measurements(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_measurements_timestamp ON measurements(timestamp);
CREATE INDEX IF NOT EXISTS idx_measurements_part_id   ON measurements(part_id);
"""


class MeasurementStore:
    """Thread-safe SQLite-backed store for Measurement records.

    Opens a fresh connection per call (low throughput is fine and avoids
    cross-thread issues with the default sqlite3 connection).
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._lock = threading.Lock()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        logger.info("MeasurementStore initialized at {}", self._db_path)

    # --- Public API ---

    def save(self, measurement: Measurement) -> int:
        """Persist a measurement and return its new database id."""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO measurements (timestamp, part_id) VALUES (?, ?)",
                (measurement.timestamp.isoformat(), measurement.part_id),
            )
            mid = cur.lastrowid
            assert mid is not None

            conn.executemany(
                "INSERT INTO port_readings (measurement_id, port, value) "
                "VALUES (?, ?, ?)",
                [(mid, r.port, r.value) for r in measurement.readings],
            )
            conn.executemany(
                "INSERT INTO judgments (measurement_id, group_index, ports, formula, computed_value, verdict) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        mid,
                        i,
                        ",".join(str(p) for p in j.ports),
                        j.formula,
                        j.computed_value,
                        j.verdict.value,
                    )
                    for i, j in enumerate(measurement.judgments, start=1)
                ],
            )
            conn.commit()

        logger.debug(
            "MeasurementStore saved measurement id={} part_id={}",
            mid, measurement.part_id,
        )
        return mid

    def load_recent(self, limit: int = 1000) -> list[Measurement]:
        """Return up to `limit` most recent measurements (oldest first)."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT id, timestamp, part_id FROM measurements "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

            measurements: list[Measurement] = []
            for mid, ts_str, part_id in reversed(rows):  # oldest first
                reading_rows = conn.execute(
                    "SELECT port, value FROM port_readings "
                    "WHERE measurement_id = ? ORDER BY port",
                    (mid,),
                ).fetchall()
                judgment_rows = conn.execute(
                    "SELECT ports, formula, computed_value, verdict FROM judgments "
                    "WHERE measurement_id = ? ORDER BY group_index",
                    (mid,),
                ).fetchall()

                readings = [PortReading(port=p, value=v) for p, v in reading_rows]
                judgments = [
                    JudgmentGroup(
                        ports=tuple(int(x) for x in ports_str.split(",")),
                        formula=formula_str,
                        computed_value=cv,
                        verdict=Verdict(verdict_str),
                    )
                    for ports_str, formula_str, cv, verdict_str in judgment_rows
                ]

                measurements.append(
                    Measurement(
                        timestamp=datetime.fromisoformat(ts_str),
                        part_id=part_id,
                        readings=readings,
                        judgments=judgments,
                    )
                )

        logger.debug("MeasurementStore loaded {} measurements", len(measurements))
        return measurements

    def count(self) -> int:
        """Return the total number of measurements in the database."""
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM measurements").fetchone()
            return int(row[0])

    # --- Internal ---

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate_formula_columns(conn)
            conn.commit()

    @staticmethod
    def _migrate_formula_columns(conn: sqlite3.Connection) -> None:
        cols = {
            row[1] for row in conn.execute("PRAGMA table_info(judgments)").fetchall()
        }
        if "formula" not in cols:
            conn.execute("ALTER TABLE judgments ADD COLUMN formula TEXT NOT NULL DEFAULT ''")
        if "computed_value" not in cols:
            conn.execute("ALTER TABLE judgments ADD COLUMN computed_value REAL NOT NULL DEFAULT 0.0")
