"""Expiração automática de recomendações ativas (spec 4.2)."""
from datetime import datetime

from app.market.reliability import is_stale


def should_expire(rec, latest_snap, now: datetime, blocks: list[str], max_age_s: int = 120, max_run_pct: float = 1.5) -> str | None:
    """Motivo da expiração ou None se a recomendação continua válida."""
    if now >= rec.expires_at:
        minutes = round((rec.expires_at - rec.created_at).total_seconds() / 60)
        return f"Prazo de validade de {minutes} min encerrado"
    if blocks:
        return "Novo bloqueio detectado: " + "; ".join(blocks)
    if latest_snap is None or is_stale(latest_snap, now, max_age_s):
        return "Dados de preço desatualizados"
    price = latest_snap.price_usd
    if price is None:
        return "Preço indisponível"
    if price <= rec.stop:
        return "Preço atingiu o stop de referência antes da entrada"
    run = (price / rec.price_observed - 1) * 100
    if run > max_run_pct:
        return f"Preço subiu {run:.2f}% desde a recomendação: entrada fora da zona"
    return None
