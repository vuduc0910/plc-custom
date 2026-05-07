"""Configuration data models."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RegisterConfig:
    """PLC register address configuration.

    Updated live without restart via RegisterManager.
    """

    port_addresses: dict[int, str] = field(default_factory=dict)
    judgment_addresses: dict[int, str] = field(default_factory=dict)
    multipliers: dict[int, float] = field(default_factory=dict)
    part_id_address: str | None = None
