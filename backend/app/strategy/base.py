"""Contrato comum das estratégias. Todas operam em candles de 5 min com horizonte de 60 min e só compram."""
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from app.domain import PairSnapshot

HORIZON = "Até 60 minutos"
DEFAULT_EXIT = "Vender no alvo 1 (ou parcial no alvo 1 e restante no alvo 2), no stop de referência ou ao fim de 60 min, o que vier primeiro"
ENTRY_BELOW = 0.005
ENTRY_ABOVE = 0.01
# Alvos em múltiplos do risco (R = preço − stop). 2,5R permite R:R líquido ≥ 1,5 quando o stop é ≥ 2,5× o custo.
TARGET1_R = 2.5
TARGET2_R = 4.0


@dataclass
class AnalysisContext:
    token: dict
    category: str
    df: pd.DataFrame
    snap: PairSnapshot
    history: list[PairSnapshot]
    now: datetime
    classification: str | None = None


@dataclass
class Signal:
    strategy: str
    price: float
    entry_low: float
    entry_high: float
    stop: float
    target1: float
    target2: float
    entry_condition: str
    invalidation: str
    rationale: list[str] = field(default_factory=list)


class Strategy:
    name: str = ""
    title: str = ""
    categories: set[str] = set()
    min_candles: int = 60
    entry: str = ""
    invalidation: str = ""
    exit: str = DEFAULT_EXIT
    indicators: list[str] = []
    limitations: str = ""

    def evaluate(self, ctx: AnalysisContext) -> Signal | None:
        raise NotImplementedError

    def describe(self) -> dict:
        return {
            "nome": self.title,
            "entrada": self.entry,
            "invalidacao": self.invalidation,
            "saida": self.exit,
            "horizonte": HORIZON,
            "indicadores": ", ".join(self.indicators),
            "limitacoes": self.limitations,
        }

    def make_signal(self, price: float, stop: float, entry_condition: str, rationale: list[str]) -> Signal | None:
        if not (price > 0 and 0 < stop < price):
            return None
        r = price - stop
        return Signal(
            strategy=self.name,
            price=price,
            entry_low=price * (1 - ENTRY_BELOW),
            entry_high=price * (1 + ENTRY_ABOVE),
            stop=stop,
            target1=price + TARGET1_R * r,
            target2=price + TARGET2_R * r,
            entry_condition=entry_condition,
            invalidation=self.invalidation,
            rationale=rationale,
        )


def fmt(v: float) -> str:
    return f"{v:.6g}"
