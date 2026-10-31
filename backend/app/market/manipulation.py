"""Detectores de manipulação de mercado (spec 3.2). São sinais indiretos, não provas."""
from dataclasses import dataclass, field
from datetime import timedelta

from app.domain import PairSnapshot

PUMP_PENALTY_PCT = 100
PUMP_BLOCK_PCT = 300
WASH_FLAG_RATIO = 30
WASH_BLOCK_RATIO = 80
ARTIFICIAL_BUY_RATIO = 6
LIQ_DROP_BLOCK = 0.30
LIQ_DROP_WINDOW = timedelta(minutes=15)
DEFAULT_MIN_LIQ = {"established": 50_000, "intermediate": 50_000, "new": 15_000}


@dataclass
class ManipulationReport:
    blocks: list[str] = field(default_factory=list)
    penalties: list[tuple[str, float]] = field(default_factory=list)
    flags: dict[str, bool] = field(default_factory=dict)


def detect_manipulation(
    snap: PairSnapshot,
    history: list[PairSnapshot],
    category: str,
    min_liquidity: dict[str, float] | None = None,
) -> ManipulationReport:
    r = ManipulationReport()
    flags = r.flags
    min_liq = (min_liquidity or DEFAULT_MIN_LIQ)[category]
    liq = snap.liquidity_usd

    if liq is None:
        r.blocks.append("Liquidez desconhecida")
    elif liq < min_liq:
        r.blocks.append(f"Liquidez de US$ {liq:,.0f} abaixo do mínimo de US$ {min_liq:,.0f}")

    ch_h1 = snap.price_change.get("h1")
    flags["pump"] = ch_h1 is not None and ch_h1 > PUMP_PENALTY_PCT
    if ch_h1 is not None and ch_h1 > PUMP_BLOCK_PCT:
        r.blocks.append(f"Alta de {ch_h1:.0f}% em 1 h: padrão de pump")
    elif flags["pump"]:
        r.penalties.append((f"Alta de {ch_h1:.0f}% em 1 h: risco de pump and dump", 3.0))

    vol24 = snap.volume.get("h24")
    flags["wash_suspeito"] = False
    if liq and vol24 is not None:
        ratio = vol24 / liq
        if ratio > WASH_BLOCK_RATIO:
            r.blocks.append(f"Volume 24 h = {ratio:.0f}× a liquidez: provável wash trading")
            flags["wash_suspeito"] = True
        elif ratio > WASH_FLAG_RATIO:
            r.penalties.append((f"Volume 24 h = {ratio:.0f}× a liquidez", 2.0))
            flags["wash_suspeito"] = True
        else:
            b, s = snap.buys.get("h24"), snap.sells.get("h24")
            ch24 = snap.price_change.get("h24")
            if ratio > 10 and b and s and abs(b - s) / max(b, s) <= 0.05 and ch24 is not None and abs(ch24) < 2:
                r.penalties.append(("Compras e vendas quase idênticas com volume alto e preço parado", 2.0))
                flags["wash_suspeito"] = True

    vol_m5 = snap.volume.get("m5")
    flags["volume_incompativel"] = bool(liq and vol_m5 is not None and vol_m5 > 0.5 * liq)
    if flags["volume_incompativel"]:
        r.penalties.append((f"Volume de 5 min equivale a {vol_m5 / liq:.0%} da liquidez", 2.0))

    b5, s5 = snap.buys.get("m5", 0), snap.sells.get("m5", 0)
    flags["pressao_artificial"] = b5 > ARTIFICIAL_BUY_RATIO * max(s5, 1) and b5 >= 10
    if flags["pressao_artificial"]:
        r.penalties.append((f"{b5} compras contra {s5} vendas em 5 min: possível atividade de bots", 1.5))

    recent = [h.liquidity_usd for h in history if h.liquidity_usd and snap.observed_at - h.observed_at <= LIQ_DROP_WINDOW]
    flags["queda_liquidez"] = False
    if recent and liq is not None:
        peak = max(recent)
        drop = 1 - liq / peak
        if drop > LIQ_DROP_BLOCK:
            r.blocks.append(f"Liquidez caiu {drop:.0%} em 15 min: possível remoção de liquidez")
            flags["queda_liquidez"] = True
    return r
