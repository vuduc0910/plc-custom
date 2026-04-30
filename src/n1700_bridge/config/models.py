"""Configuration data models."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RegisterConfig:
    """PLC register address configuration.

    Updated live without restart via RegisterManager.
    """

    port_addresses: dict[int, str] = field(default_factory=dict)  # {1: "D100", 2: "D102", ...}
    judgment_addresses: dict[int, str] = field(
        default_factory=dict
    )  # {1: "M200", 2: "M201", 3: "M202"}
    part_id_address: str | None = None  # TODO(client-Q3.1): Part ID to PLC TBD.
