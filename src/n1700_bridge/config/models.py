from dataclasses import dataclass, field


@dataclass(frozen=True)
class RegisterConfig:

    port_addresses: dict[int, str] = field(default_factory=lambda: {
        i: f"D{1198 + i * 2}" for i in range(1, 10)
    })
    judgment_addresses: dict[int, str] = field(default_factory=dict)
    port_verdict_addresses: dict[int, str] = field(default_factory=lambda: {
        i: f"D{1130 + i}" for i in range(1, 10)
    })
    multiplier: float = 1.0
    zeros: dict[int, float] = field(default_factory=dict)
    judgment_groups: list[dict[str, object]] = field(default_factory=list)
    template_path: str | None = None
    template_input_cells: list[str] = field(default_factory=list)
    port_verdict_cells: list[str] = field(default_factory=list)
    part_id_address: str | None = None
