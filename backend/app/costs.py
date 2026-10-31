"""Custos estimados de uma operação de ida e volta (spec 3.6).

A taxa da FOMO só aparece na tela de confirmação do app, por isso é configurável; os demais
componentes são estimativas declaradas como tais.
"""
from dataclasses import asdict, dataclass

from app.chains import Chain


@dataclass(frozen=True)
class CostEstimate:
    fomo_fee_pct: float
    pool_fee_pct: float
    impact_pct: float
    slippage_pct: float
    gas_usd: float
    round_trip_pct: float
    round_trip_usd: float

    def as_dict(self) -> dict:
        return asdict(self)


def estimate_costs(chain: Chain, amount_usd: float, liquidity_usd: float | None, cfg: dict) -> CostEstimate:
    fomo_pct = float(cfg["cost.fomo_fee_pct"])
    fomo_min = float(cfg.get("cost.fomo_min_fee_usd", 0.0))
    pool = float(cfg["cost.pool_fee_pct"])
    slip = float(cfg["cost.base_slippage_pct"])
    gas = float(cfg[f"cost.gas_usd.{chain.value}"])
    if not liquidity_usd or amount_usd <= 0:
        inf = float("inf")
        return CostEstimate(fomo_pct, pool, inf, slip, gas, inf, inf)
    fomo = max(fomo_pct, fomo_min / amount_usd * 100)  # taxa mínima por ordem pesa muito em valores pequenos
    impact = amount_usd / (liquidity_usd / 2) * 100
    per_side = fomo + pool + impact + slip
    round_trip = 2 * per_side + 2 * gas / amount_usd * 100
    return CostEstimate(fomo, pool, impact, slip, gas, round_trip, round_trip / 100 * amount_usd)
