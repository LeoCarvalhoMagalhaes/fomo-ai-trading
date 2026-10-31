"""Limpeza periódica: o banco gratuito online tem 500 MB, e snapshots de 240 tokens por minuto ocupam ~60 MB/dia.

Avaliações, recomendações e operações nunca são apagadas: são o histórico e alimentam a calibração.
"""
from datetime import datetime, timedelta

from sqlalchemy import delete

from app.db.models import Candle, Event, Notification, Snapshot
from app.db.session import Database


def prune_old_data(db: Database, now: datetime, snapshots_hours: float, candles_days: float, logs_days: float) -> dict:
    cutoffs = {
        "snapshots": (Snapshot, Snapshot.observed_at, now - timedelta(hours=snapshots_hours)),
        "candles": (Candle, Candle.ts, now - timedelta(days=candles_days)),
        "events": (Event, Event.created_at, now - timedelta(days=logs_days)),
        "notifications": (Notification, Notification.created_at, now - timedelta(days=logs_days)),
    }
    removed = {}
    with db.session() as s:
        for name, (model, column, cutoff) in cutoffs.items():
            removed[name] = s.execute(delete(model).where(column < cutoff)).rowcount
    return removed
