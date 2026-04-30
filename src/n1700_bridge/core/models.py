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
    """Groups 3 ports into one OK/NG verdict (per spec slide 5).

    Note: exact grouping logic TBD — see clarification Q1.4. Default 3-3-3.
    """

    # TODO(client-Q1.4): Confirm 3-3-3 grouping with client.
    ports: tuple[int, int, int]  # e.g. (1, 2, 3)
    verdict: Verdict


@dataclass
class Measurement:
    """A complete measurement cycle result."""

    timestamp: datetime
    part_id: str  # Barcode content
    readings: list[PortReading]  # 9 items
    judgments: list[JudgmentGroup] = field(default_factory=list)  # 3 items


@dataclass(frozen=True)
class Threshold:
    """OK/NG threshold for a single port."""

    # TODO(client-Q1.2): Confirm threshold source with client.
    port: int
    lower: float
    upper: float
