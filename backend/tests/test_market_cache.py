"""Preços recentes ficam na memória: o banco online gratuito cobra tráfego de saída (5 GB/mês)."""
from datetime import timedelta

from sqlalchemy import event

from app.collector.service import MarketService
from tests.test_engine import AlwaysBuy, build, now


def reads_from(db, *tables):
    seen = []

    def listener(conn, cursor, statement, *args):
        if statement.lstrip().upper().startswith("SELECT") and any(f"FROM {t}" in statement for t in tables):
            seen.append(statement)

    event.listen(db.engine, "before_cursor_execute", listener)
    return seen


def snapshot_reads(db):
    return reads_from(db, "snapshots")


HOT_TABLES = ("snapshots", "candles", "security_reports", "tokens")


async def test_steady_state_cycle_does_not_reread_market_data():
    db, market, engine, *_ = await build([AlwaysBuy()], min_score=101)  # sinais vetados: sem recomendação ativa
    await engine.run_cycle("full", "teste")
    reads = reads_from(db, *HOT_TABLES)
    await market.refresh_tier1()
    await engine.run_cycle("quick", "teste")
    market.market_regime()
    market.tier2_tokens()
    assert reads == []


async def test_classification_change_is_seen_without_database_read():
    db, market, engine, *_ = await build([])
    token = market.tier2_tokens()[0]
    await engine._update_classification(token, "C", ["teste"], market.latest_snapshot(token.id))
    assert all(t.id != token.id for t in market.tier2_tokens())
    restarted = type(market)(db, market.dex, market.gecko, market.goplus, market.runtime)
    assert all(t.id != token.id for t in restarted.tier2_tokens())  # e foi gravada no banco


async def test_new_candles_and_security_reports_replace_cached_ones():
    db, market, *_ = await build([])
    token = market.tier2_tokens()[0]
    before = market.candles_df(token.id)
    market.gecko.ohlcv_shift = 0.5
    market._candles_at.clear()
    await market.refresh_candles()
    after = market.candles_df(token.id)
    assert after["close"].iloc[-1] > before["close"].iloc[-1]
    first = await market.ensure_security(token)
    assert {r.source for r in first} >= {"goplus"}
    assert market.latest_security(token.id) == first


async def test_restart_rebuilds_token_list_from_database():
    db, market, *_ = await build([])
    ids = [t.id for t in market.tier2_tokens()]
    restarted = type(market)(db, market.dex, market.gecko, market.goplus, market.runtime)
    assert [t.id for t in restarted.tier2_tokens()] == ids


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
