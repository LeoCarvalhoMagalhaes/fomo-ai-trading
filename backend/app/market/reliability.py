"""Nota de confiabilidade (0–1) de um snapshot: fonte, idade e concordância entre fontes."""
from datetime import datetime

DIVERGENCE_LIMIT = 0.02
DIVERGENCE_FACTOR = 0.6
FRESH_S = 30


def is_stale(snap, now: datetime, max_age_s: int = 120) -> bool:
    return (now - snap.observed_at).total_seconds() > max_age_s


def reliability(snap, other_price: float | None, now: datetime, max_age_s: int = 120) -> float:
    if is_stale(snap, now, max_age_s):
        return 0.0
    score = snap.reliability
    if other_price and snap.price_usd:
        if abs(snap.price_usd - other_price) / other_price > DIVERGENCE_LIMIT:
            score *= DIVERGENCE_FACTOR
    age = (now - snap.observed_at).total_seconds()
    if age > FRESH_S:
        score *= 1 - 0.5 * (age - FRESH_S) / (max_age_s - FRESH_S)
    return round(score, 4)
