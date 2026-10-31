"""Backtest com quadros SINTÉTICOS controlados."""
import pandas as pd

from app.backtest.calibration import calibrate, isotonic_fit
from app.backtest.engine import exit_for, simulate, time_split
from app.chains import Chain
from app.config import DEFAULT_RUNTIME
from app.strategy.base import Strategy
from tests.test_strategies import BASE

CFG = dict(DEFAULT_RUNTIME, **{"cost.fomo_min_fee_usd": 0.0})


def bars(rows):
    df = pd.DataFrame([dict(BASE, **r) for r in rows])
    df.index = pd.date_range("2026-10-01", periods=len(df), freq="5min", tz="UTC")
    return df


def test_same_bar_target_and_stop_counts_stop():
    future = bars([{"high": 120.0, "low": 80.0, "close": 100.0}])
    hit, price, idx = exit_for(future, stop=90.0, target=110.0)
    assert hit == "stop" and price == 90.0 and idx == 0


def test_exit_target_then_time():
    future = bars([{"high": 105.0, "low": 99.0}, {"high": 111.0, "low": 101.0}])
    assert exit_for(future, 90.0, 110.0)[0] == "alvo1"
    future = bars([{"high": 105.0, "low": 99.0, "close": 103.0}])
    hit, price, _ = exit_for(future, 90.0, 110.0)
    assert hit == "tempo" and price == 103.0


def test_time_split_no_shuffle():
    items = list(range(10))
    train, val, test = time_split(items)
    assert train == [0, 1, 2, 3, 4, 5] and val == [6, 7] and test == [8, 9]


class EveryTenBars(Strategy):
    name = "teste_10"
    categories = {"established"}
    min_candles = 5

    def evaluate(self, ctx):
        if len(ctx.df) % 10:
            return None
        p = float(ctx.df["close"].iloc[-1])
        return self.make_signal(p, p * 0.9, "teste", [])


def test_simulate_applies_costs_and_no_overlap():
    df = bars([{} for _ in range(60)])  # preço parado em 100
    trades = simulate({"T": df}, [EveryTenBars()], CFG, {"T": Chain.solana}, {"T": "established"}, {"T": 1_000_000}, max_bars=12)
    assert trades and all(t.outcome == "tempo" for t in trades)
    assert all(t.pnl_pct < 0 for t in trades)  # preço parado: perde exatamente os custos
    for a, b in zip(trades, trades[1:]):
        assert b.entry_ts > a.exit_ts


def test_isotonic_monotonic():
    f = isotonic_fit([1, 2, 3, 4, 5, 6], [0, 1, 0, 1, 1, 1])
    vals = [f(x) for x in [1, 2, 3, 4, 5, 6]]
    assert vals == sorted(vals)
    assert f(1) == 0.0 and abs(f(2) - 0.5) < 1e-9 and abs(f(3) - 0.5) < 1e-9 and f(6) == 1.0


def test_calibrate_returns_none_under_200():
    assert calibrate([80] * 199, [1] * 199) is None
    cal = calibrate([80 + i % 20 for i in range(300)], [i % 2 for i in range(300)])
    assert cal is not None and cal.n == 300 and 0 <= cal.predict(85) <= 1


def test_backtest_from_db_runs_on_recorded_candles():
    from datetime import timedelta

    from app.backtest.report import backtest_from_db
    from app.db.models import Token
    from app.db.session import Database
    from app.domain import Candle
    from tests.conftest import NOW, test_db_url

    db = Database(test_db_url())
    with db.session() as s:
        t = Token(chain="solana", address="X", symbol="X", name="X", category="established")
        s.add(t)
        s.flush()
        tid = t.id
    candles = [Candle(ts=NOW + timedelta(minutes=5 * i), open=1 + (i % 7) * 0.01, high=1.05 + (i % 7) * 0.01,
                      low=0.95 + (i % 7) * 0.01, close=1 + (i % 5) * 0.01, volume=100 + i) for i in range(200)]
    db.upsert_candles(tid, "5m", candles, "teste")
    rep = backtest_from_db(db, CFG, {tid: 1_000_000})
    assert rep["status"] == "ok" and rep["ativos"] == 1
    assert set(rep["resultado"]) == {"treino", "validacao", "teste", "total"}


def test_filter_report_requires_200_test_samples():
    from app.backtest.report import filter_report
    from app.db.models import Evaluation, Token
    from app.db.session import Database
    from tests.conftest import NOW, test_db_url

    db = Database(test_db_url())
    with db.session() as s:
        t = Token(chain="solana", address="X", symbol="X", name="X")
        s.add(t)
        s.flush()
        for i in range(300):
            s.add(Evaluation(token_id=t.id, decision="RECOMENDADA" if i % 3 == 0 else "REJEITADA", score=70 + i % 30,
                             outcome_at=NOW, outcome_hit="alvo1" if i % 2 else "stop", outcome_return_pct=1.0, price=1.0))
    rep = filter_report(db)
    assert rep["recomendada"]["n"] == 100 and rep["rejeitada"]["n"] == 200
    assert rep["calibracao"]["status"] == "insuficiente"
