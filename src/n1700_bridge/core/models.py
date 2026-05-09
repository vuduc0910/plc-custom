from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Verdict(str, Enum):

    OK = "OK"
    NG = "NG"
    PENDING = "PENDING"


@dataclass(frozen=True)
class PortReading:

    port: int
    value: float


@dataclass(frozen=True)
class PortVerdict:

    port: int
    verdict: Verdict


@dataclass(frozen=True)
class JudgmentGroup:

    group_name: str
    output_cell: str
    computed_value: float
    verdict: Verdict


@dataclass
class Measurement:

    timestamp: datetime
    part_id: str
    readings: list[PortReading]
    judgments: list[JudgmentGroup] = field(default_factory=list)
    port_verdicts: list[PortVerdict] = field(default_factory=list)


@dataclass(frozen=True)
class JudgmentGroupConfig:

    name: str
    output_cell: str


@dataclass(frozen=True)
class ExcelTemplateConfig:

    path: str
    sheet_name: str
    input_cells: tuple[str, ...]
    port_verdict_cells: tuple[str, ...] = (
        "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9", "H10",
    )
