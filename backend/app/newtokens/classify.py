"""Classificação de tokens novos em A (oportunidade potencial), B (acompanhar) e C (evitar). Spec 3.3."""
from datetime import datetime, timedelta
from typing import Literal

from app.domain import PairSnapshot
from app.market.manipulation import ManipulationReport
from app.security.rules import SecurityVerdict

MIN_AGE = timedelta(minutes=30)
LIQUIDITY_WINDOW = timedelta(minutes=15)


def _rate_ok(snap: PairSnapshot) -> tuple[bool, str]:
    counts = snap.buyers if snap.buyers else snap.buys
    label = "compradores únicos" if snap.buyers else "compras"
    m5, h1 = counts.get("m5"), counts.get("h1")
    if m5 is None or h1 is None:
        return False, f"Sem dado de {label} por janela"
    avg = h1 / 12
    if m5 < avg:
        return False, f"{label.capitalize()} desacelerando: {m5} em 5 min contra média de {avg:.1f} por 5 min na última hora (compradores)"
    return True, ""


def classify_new_token(
    snap: PairSnapshot,
    history: list[PairSnapshot],
    verdict: SecurityVerdict,
    manip: ManipulationReport,
    now: datetime,
) -> tuple[Literal["A", "B", "C"], list[str]]:
    if verdict.blocks or manip.blocks:
        return "C", verdict.blocks + manip.blocks

    reasons: list[str] = []
    if snap.pair_created_at is None or now - snap.pair_created_at < MIN_AGE:
        reasons.append("Menos de 30 min de negociação: aguardar confirmação")
    if not (len(verdict.sources) >= 2 or verdict.coverage >= 1.0):
        reasons.append(f"Segurança confirmada por uma única fonte com cobertura de {verdict.coverage:.0%}")
    ok, why = _rate_ok(snap)
    if not ok:
        reasons.append(why)

    window = [h for h in history if h.liquidity_usd and now - h.observed_at <= LIQUIDITY_WINDOW + timedelta(minutes=1)]
    if not window:
        reasons.append("Sem histórico suficiente para avaliar a liquidez")
    elif snap.liquidity_usd is None or snap.liquidity_usd < 0.95 * window[0].liquidity_usd:
        reasons.append("Queda de liquidez nos últimos 15 min")

    return ("B", reasons) if reasons else ("A", ["Sem bloqueios, segurança coberta, compradores crescendo e liquidez estável"])
