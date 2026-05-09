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
    PortVerdict,
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

CREATE TABLE IF NOT EXISTS port_verdicts (
    measurement_id  INTEGER NOT NULL,
    port            INTEGER NOT NULL,
    verdict         TEXT    NOT NULL,
    PRIMARY KEY (measurement_id, port),
    FOREIGN KEY (measurement_id) REFERENCES measurements(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS judgments (
    measurement_id  INTEGER NOT NULL,
    group_index     INTEGER NOT NULL,
    group_name      TEXT    NOT NULL DEFAULT '',
    output_cell     TEXT    NOT NULL DEFAULT '',
    computed_value  REAL    NOT NULL DEFAULT 0.0,
    verdict         TEXT    NOT NULL,
    PRIMARY KEY (measurement_id, group_index),
    FOREIGN KEY (measurement_id) REFERENCES measurements(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_measurements_timestamp ON measurements(timestamp);
CREATE INDEX IF NOT EXISTS idx_measurements_part_id   ON measurements(part_id);
"""


class MeasurementStore:

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._lock = threading.Lock()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        logger.info("MeasurementStore initialized at {}", self._db_path)

    def save(self, measurement: Measurement) -> int:
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
                "INSERT INTO port_verdicts (measurement_id, port, verdict) "
                "VALUES (?, ?, ?)",
                [(mid, pv.port, pv.verdict.value) for pv in measurement.port_verdicts],
            )
            conn.executemany(
                "INSERT INTO judgments "
                "(measurement_id, group_index, group_name, output_cell, computed_value, verdict) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        mid,
                        i,
                        j.group_name,
                        j.output_cell,
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
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT id, timestamp, part_id FROM measurements "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

            measurements: list[Measurement] = []
            for mid, ts_str, part_id in reversed(rows):
                reading_rows = conn.execute(
                    "SELECT port, value FROM port_readings "
                    "WHERE measurement_id = ? ORDER BY port",
                    (mid,),
                ).fetchall()
                verdict_rows = conn.execute(
                    "SELECT port, verdict FROM port_verdicts "
                    "WHERE measurement_id = ? ORDER BY port",
                    (mid,),
                ).fetchall()
                judgment_rows = conn.execute(
                    "SELECT group_name, output_cell, computed_value, verdict "
                    "FROM judgments "
                    "WHERE measurement_id = ? ORDER BY group_index",
                    (mid,),
                ).fetchall()

                readings = [PortReading(port=p, value=v) for p, v in reading_rows]
                port_verdicts = [
                    PortVerdict(port=p, verdict=Verdict(v)) for p, v in verdict_rows
                ]
                judgments = [
                    JudgmentGroup(
                        group_name=gn,
                        output_cell=oc,
                        computed_value=cv,
                        verdict=Verdict(vd),
                    )
                    for gn, oc, cv, vd in judgment_rows
                ]

                measurements.append(
                    Measurement(
                        timestamp=datetime.fromisoformat(ts_str),
                        part_id=part_id,
                        readings=readings,
                        judgments=judgments,
                        port_verdicts=port_verdicts,
                    )
                )

        logger.debug("MeasurementStore loaded {} measurements", len(measurements))
        return measurements

    def count(self) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM measurements").fetchone()
            return int(row[0])

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate_legacy_columns(conn)
            conn.commit()

    @staticmethod
    def _migrate_legacy_columns(conn: sqlite3.Connection) -> None:
        cols = {
            row[1] for row in conn.execute("PRAGMA table_info(judgments)").fetchall()
        }

        if "ports" in cols or "formula" in cols:
            conn.execute("DROP TABLE IF EXISTS judgments")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS judgments (
                    measurement_id  INTEGER NOT NULL,
                    group_index     INTEGER NOT NULL,
                    group_name      TEXT    NOT NULL DEFAULT '',
                    output_cell     TEXT    NOT NULL DEFAULT '',
                    computed_value  REAL    NOT NULL DEFAULT 0.0,
                    verdict         TEXT    NOT NULL,
                    PRIMARY KEY (measurement_id, group_index),
                    FOREIGN KEY (measurement_id)
                        REFERENCES measurements(id) ON DELETE CASCADE
                )
            """)
            return

        if "group_name" not in cols:
            conn.execute(
                "ALTER TABLE judgments ADD COLUMN group_name TEXT NOT NULL DEFAULT ''"
            )
        if "output_cell" not in cols:
            conn.execute(
                "ALTER TABLE judgments ADD COLUMN output_cell TEXT NOT NULL DEFAULT ''"
            )
        if "computed_value" not in cols:
            conn.execute(
                "ALTER TABLE judgments ADD COLUMN computed_value REAL NOT NULL DEFAULT 0.0"
            )
