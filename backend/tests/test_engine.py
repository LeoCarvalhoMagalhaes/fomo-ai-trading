"""Ciclo de análise com provedores FALSOS em memória (sem rede). Dados sintéticos identificados como tal."""
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.chains import Chain
from app.collector.service import MarketService
from app.db.models import Evaluation, Recommendation, Token, Trade
from app.db.runtime_settings import RuntimeSettings
from app.db.session import Database
from app.domain import Candle, PairSnapshot, SecurityReport
from app.notify.hub import Notifier
from app.providers.base import ProviderError, ProviderHealth
from app.recommend.engine import AnalysisEngine
from app.recommend.format import NO_TRADE_MESSAGE
from app.strategy.base import Strategy


def now():
    return datetime.now(timezone.utc)


class FakeDex:
    name = "dexscreener"

    def __init__(self):
        self.health = ProviderHealth("dexscreener")
        self.price = 1.0
        self.fail = False

    async def tokens(self, chain, addresses):
        if self.fail:
            raise ProviderError("dexscreener", 500, "fora do ar")
        return [snap(a, self.price) for a in addresses]


class FakeGecko:
    name = "geckoterminal"

    def __init__(self):
        self.health = ProviderHealth("geckoterminal")
        self.fail = False

    async def new_pools(self, chain):
        if self.fail:
            raise ProviderError("geckoterminal", 500, "fora do ar")
        return [snap("TOK", 1.0, source="geckoterminal")] if chain == Chain.solana else []

    async def trending_pools(self, chain, duration="1h"):
        if self.fail:
            raise ProviderError("geckoterminal", 500, "fora do ar")
        return []

    async def ohlcv(self, chain, pool, aggregate=5, limit=100):
        t0 = now().replace(second=0, microsecond=0) - timedelta(minutes=5 * 80)
        return [Candle(ts=t0 + timedelta(minutes=5 * i), open=0.9 + i * 0.001, high=0.91 + i * 0.001,
                       low=0.89 + i * 0.001, close=0.9 + i * 0.001, volume=1000) for i in range(80)]

    async def token_info(self, chain, address):
        return SecurityReport(chain=chain, token_address=address, source="geckoterminal", observed_at=now(),
                              flags={"mintable": False, "freezable": False, "honeypot": None}, top10_pct=20.0)


class FakeGoPlus:
    name = "goplus"

    def __init__(self):
        self.health = ProviderHealth("goplus")

    async def token_security(self, chain, address):
        return SecurityReport(chain=chain, token_address=address, source="goplus", observed_at=now(),
                              flags={"mintable": False, "freezable": False, "balance_mutable": False,
                                     "non_transferable": False, "transfer_hook": False},
                              taxes={"transfer": 0.0}, top10_pct=20.0, holder_count=50_000)


def snap(address, price, source="dexscreener"):
    return PairSnapshot(chain=Chain.solana, token_address=address, pair_address="POOL", symbol="TOK", name="Token",
                        price_usd=price, liquidity_usd=2_000_000, volume={"m5": 5_000, "h1": 60_000, "h24": 900_000},
                        buys={"m5": 30, "h1": 300, "h24": 4000}, sells={"m5": 20, "h1": 250, "h24": 3500},
                        price_change={"h1": 2.0, "h24": 5.0}, pair_created_at=now() - timedelta(days=60),
                        observed_at=now(), source=source)


class AlwaysBuy(Strategy):
    name = "teste_sempre_compra"
    title = "Estratégia de teste"
    categories = {"established", "intermediate", "new"}
    min_candles = 20
    entry = invalidation = limitations = "teste"
    indicators = ["nenhum"]

    def evaluate(self, ctx):
        price = ctx.snap.price_usd
        return self.make_signal(price, price * 0.9, "teste", ["sinal sintético de teste"])


async def build(strategies, min_score=0):
    db = Database("sqlite:///:memory:")
    rs = RuntimeSettings(db)
    rs.set("rec.min_score", min_score, actor="teste")
    rs.set("cost.fomo_min_fee_usd", 0.0, actor="teste")
    dex, gecko, goplus = FakeDex(), FakeGecko(), FakeGoPlus()
    market = MarketService(db, dex, gecko, goplus, rs)
    sent = []

    async def broadcast(msg):
        sent.append(msg)

    engine = AnalysisEngine(db, market, Notifier(db, []), rs, broadcast, strategies=strategies)
    await market.discover()
    await market.refresh_tier1()
    await market.refresh_candles()
    return db, market, engine, dex, gecko


def count(db, stmt):
    with db.session() as s:
        return s.scalar(stmt)


async def test_full_cycle_without_candidates_returns_no_trade_message():
    db, market, engine, *_ = await build([])
    result = await engine.run_cycle("full", "teste")
    assert result.message == NO_TRADE_MESSAGE
    assert result.analyzed == 1 and result.recommendations == 0
    assert count(db, select(func.count()).select_from(Evaluation).where(Evaluation.decision == "REJEITADA")) == 1


async def test_full_cycle_rejections_are_recorded():
    db, market, engine, *_ = await build([AlwaysBuy()], min_score=100)
    result = await engine.run_cycle("full", "teste")
    assert result.recommendations == 0
    with db.session() as s:
        ev = s.scalars(select(Evaluation).where(Evaluation.strategy == "teste_sempre_compra")).one()
    assert ev.decision == "REJEITADA" and any("Pontuação" in r for r in ev.reasons)


async def test_approved_recommendation_is_created_with_text():
    db, market, engine, *_ = await build([AlwaysBuy()])
    result = await engine.run_cycle("full", "teste")
    assert result.recommendations == 1
    with db.session() as s:
        rec = s.scalars(select(Recommendation)).one()
    assert rec.status == "ATIVA" and "DIREÇÃO: Compra" in rec.text and rec.amount_usd >= 5


async def test_cycle_lock_prevents_duplicates():
    db, market, engine, *_ = await build([AlwaysBuy()])
    await asyncio.gather(engine.run_cycle("full", "a"), engine.run_cycle("quick", "b"))
    assert count(db, select(func.count()).select_from(Recommendation)) == 1


async def test_blocked_when_all_providers_down():
    db, market, engine, dex, gecko = await build([AlwaysBuy()])
    dex.fail = gecko.fail = True
    for t in market.health_list():
        t.record_failure("fora do ar", now())
    with db.session() as s:
        for row in s.scalars(select(Token)):
            row.last_seen = now() - timedelta(minutes=10)
    market._last_fresh = now() - timedelta(minutes=10)
    result = await engine.run_cycle("full", "teste")
    assert "BLOQUEADO" in result.message and result.recommendations == 0


async def test_sim_ledger_auto_opens_on_approval():
    db, market, engine, *_ = await build([AlwaysBuy()])
    await engine.run_cycle("full", "teste")
    with db.session() as s:
        trade = s.scalars(select(Trade)).one()
    assert trade.ledger == "SIM" and trade.status == "OPEN" and trade.entry_price > 1.0  # slippage aplicado


async def test_monitor_closes_sim_on_stop():
    db, market, engine, dex, _ = await build([AlwaysBuy()])
    await engine.run_cycle("full", "teste")
    dex.price = 0.85  # abaixo do stop de 0,9
    await market.refresh_tier1()
    await engine.monitor_positions()
    with db.session() as s:
        trade = s.scalars(select(Trade)).one()
    assert trade.status == "CLOSED" and trade.close_reason == "stop" and trade.pnl_usd < 0


async def test_execution_report_opens_real_trade_and_triggers_cycle():
    db, market, engine, *_ = await build([AlwaysBuy()])
    await engine.run_cycle("full", "teste")
    with db.session() as s:
        rec_id = s.scalars(select(Recommendation.id)).one()
    trade_id = await engine.report_execution(rec_id, price=1.001, amount_usd=7.0, fee_usd=0.04, executed_at=now())
    with db.session() as s:
        trade = s.get(Trade, trade_id)
        rec = s.get(Recommendation, rec_id)
    assert trade.ledger == "REAL" and trade.entry_price == 1.001 and rec.status == "EXECUTADA"
    assert engine.last_trigger == "execucao"


async def test_quick_cycle_refreshes_stale_prices_instead_of_blocking():
    db, market, engine, *_ = await build([])
    market._last_fresh = now() - timedelta(minutes=10)
    result = await engine.run_cycle("quick", "teste")
    assert "BLOQUEADO" not in result.message


async def test_gecko_security_only_for_new_tokens():
    db, market, engine, dex, gecko = await build([])
    calls = []
    original = gecko.token_info

    async def spy(chain, address):
        calls.append(address)
        return await original(chain, address)

    gecko.token_info = spy
    with db.session() as s:
        tok = s.scalars(select(Token)).one()
    await market.ensure_security(tok)
    assert calls == []  # estabelecido: só GoPlus
    tok.category = "new"
    await market.ensure_security(tok)
    assert calls == ["TOK"]


async def test_full_cycle_does_not_fetch_candles():
    db, market, engine, dex, gecko = await build([])
    calls = []

    async def spy(*a, **k):
        calls.append(a)
        return []

    gecko.ohlcv = spy
    market._candles_at.clear()  # candles vencidos: só a tarefa contínua deve buscá-los
    await engine.run_cycle("full", "teste")
    assert calls == []
