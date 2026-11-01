"""Calibração estatística nota → probabilidade de atingir o alvo 1 antes do stop (regressão isotônica, PAV).

Só existe estimativa com amostra suficiente fora da amostra; caso contrário a resposta é "sem estimativa confiável".
"""
from bisect import bisect_right
from dataclasses import dataclass
from typing import Callable

MIN_SAMPLES = 200


def isotonic_fit(x: list[float], y: list[float]) -> Callable[[float], float]:
    pairs = sorted(zip(x, y))
    blocks: list[list[float]] = []  # [soma, contagem, x_inicial]
    for xi, yi in pairs:
        blocks.append([yi, 1, xi])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            s, c, _ = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += c
    starts = [b[2] for b in blocks]
    values = [b[0] / b[1] for b in blocks]

    def predict(v: float) -> float:
        """Função em degraus: valor do último bloco que começa em x ≤ v."""
        return values[max(0, bisect_right(starts, v) - 1)]

    return predict


@dataclass
class Calibrator:
    fn: Callable[[float], float]
    n: int

    def predict(self, score: float) -> float:
        return self.fn(score)

    def describe(self, score: float) -> str:
        return f"{self.predict(score):.0%} de chance estimada de atingir o alvo 1 antes do stop (calibrado em {self.n} avaliações fora da amostra)"


def calibrate(scores: list[float], outcomes: list[int], min_samples: int = MIN_SAMPLES) -> Calibrator | None:
    if len(scores) < min_samples:
        return None
    return Calibrator(isotonic_fit(scores, outcomes), len(scores))
