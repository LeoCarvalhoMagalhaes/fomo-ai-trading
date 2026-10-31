"""Preços recentes ficam na memória: o banco online gratuito cobra tráfego de saída (5 GB/mês)."""
from datetime import timedelta

from sqlalchemy import event

from app.collector.service import MarketService
from tests.test_engine import build, now


def snapshot_reads(db):
    seen = []

    def listener(conn, cursor, statement, *args):
        if "FROM snapshots" in statement:
            seen.append(statement)

    event.listen(db.engine, "before_cursor_execute", listener)
    return seen


async def test_recent_prices_are_served_from_memory():
    db, market, *_ = await build([])
    token = market.tier2_tokens()[0]
    reads = snapshot_reads(db)
    assert market.latest_snapshot(token.id) is not None
    assert len(market.history(token.id, now() - timedelta(minutes=30))) >= 1
    market.market_regime()
    market.tier2_tokens()
    assert reads == []


async def test_restart_loads_recent_prices_from_database_once():
    db, market, *_ = await build([])
    token = market.tier2_tokens()[0]
    since = now() - timedelta(minutes=30)
    cached = market.history(token.id, since)
    reads = snapshot_reads(db)
    restarted = MarketService(db, market.dex, market.gecko, market.goplus, market.runtime)
    assert len(reads) == 1  # uma consulta só, ao iniciar
    assert [s.observed_at for s in restarted.history(token.id, since)] == [s.observed_at for s in cached]
    assert restarted.latest_snapshot(token.id).observed_at == cached[-1].observed_at
    assert len(reads) == 1


async def test_history_older_than_memory_window_uses_database():
    db, market, *_ = await build([])
    token = market.tier2_tokens()[0]
    reads = snapshot_reads(db)
    market.history(token.id, now() - timedelta(hours=3))
    assert reads
