"""Domain models for N1700 Bridge."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Verdict(str, Enum):
    """Measurement verdict."""

    OK = "OK"
    NG = "NG"
    PENDING = "PENDING"


@dataclass(frozen=True)
class PortReading:
    """A single port measurement reading."""

    port: int  # 1..9
    value: float


@dataclass(frozen=True)
class JudgmentGroup:
    ports: tuple[int, ...]
    formula: str
    computed_value: float
    verdict: Verdict


@dataclass
class Measurement:
    timestamp: datetime
    part_id: str
    readings: list[PortReading]
    judgments: list[JudgmentGroup] = field(default_factory=list)


@dataclass(frozen=True)
class FormulaGroupConfig:
    ports: tuple[int, ...]
    formula: str
    lower: float
    upper: float
