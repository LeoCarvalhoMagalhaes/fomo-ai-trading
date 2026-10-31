"""Detectores de manipulação de mercado (spec 3.2)."""
from dataclasses import dataclass, field


@dataclass
class ManipulationReport:
    blocks: list[str] = field(default_factory=list)
    penalties: list[tuple[str, float]] = field(default_factory=list)
    flags: dict[str, bool] = field(default_factory=dict)
