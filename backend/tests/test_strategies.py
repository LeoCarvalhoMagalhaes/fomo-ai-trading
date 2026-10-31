"""Testes com quadros SINTÉTICOS: as colunas de indicadores são definidas diretamente para cada cenário."""
from datetime import timedelta

import pandas as pd

from app.chains import Chain
from app.domain import PairSnapshot
from app.strategy.base import AnalysisContext
from app.strategy.registry import ALL_STRATEGIES, run_strategies
from tests.conftest import NOW

BASE = dict(open=100.0, high=101.0, low=99.0, close=100.0, volume=100.0, ema9=100.0, ema20=100.0, ema21=100.0,
            ema50=100.0, sma20=100.0, rsi14=50.0, macd=0.0, macd_signal=0.0, macd_hist=0.0, bb_mid=100.0,
            bb_up=104.0, bb_low=96.0, atr14=2.0, rel_vol=1.0, hh24=101.0, ll24=99.0, vwap=100.0)


def frame(n=80, **tail):
    """n linhas base; cada kwarg é uma lista aplicada às últimas linhas daquela coluna."""
    rows = [dict(BASE) for _ in range(n)]
    for col, values in tail.items():
        for i, v in enumerate(values):
            rows[n - len(values) + i][col] = v
    idx = pd.date_range(end=NOW, periods=n, freq="5min")
    return pd.DataFrame(rows, index=idx)


def snap(price=100.0, age=timedelta(days=60), liq=1_000_000, buys_m5=30, sells_m5=15, buys_h1=240, sells_h1=150):
    return PairSnapshot(chain=Chain.solana, token_address="T", pair_address="P", symbol="T", name="T",
                        price_usd=price, liquidity_usd=liq, buys={"m5": buys_m5, "h1": buys_h1},
                        sells={"m5": sells_m5, "h1": sells_h1}, pair_created_at=NOW - age,
                        observed_at=NOW, source="dexscreener")


def ctx(df, category="established", s=None, classification=None, history=None):
    s = s or snap(price=float(df["close"].iloc[-1]))
    return AnalysisContext(token={"symbol": "T"}, category=category, df=df, snap=s, history=history or [s],
                           now=NOW, classification=classification)


def names(signals):
    return {s.strategy for s in signals}


def by_name(name):
    return next(s for s in ALL_STRATEGIES if s.name == name)


# 1. established_pullback
def test_pullback_positive():
    df = frame(ema20=[100.0], ema50=[95.0], close=[100.5], low=[99.5], rsi14=[44.0, 47.0])
    sig = by_name("established_pullback").evaluate(ctx(df))
    assert sig is not None
    assert sig.stop < 100.5 < sig.target1 < sig.target2
    r = 100.5 - sig.stop
    assert abs(sig.target1 - (100.5 + 1.5 * r)) < 1e-9


def test_pullback_rsi_falling_rejected():
    df = frame(ema20=[100.0], ema50=[95.0], close=[100.5], rsi14=[50.0, 47.0])
    assert by_name("established_pullback").evaluate(ctx(df)) is None


def test_pullback_only_established():
    df = frame(ema20=[100.0], ema50=[95.0], close=[100.5], rsi14=[44.0, 47.0])
    assert "established_pullback" not in names(run_strategies(ctx(df, category="new", classification="A")))


# 2. uptrend_momentum
def test_uptrend_momentum_positive():
    df = frame(ema9=[103.0], ema21=[101.0], ema50=[98.0], macd_hist=[0.1, 0.2, 0.3], rsi14=[62.0],
               close=[104.0], vwap=[101.0])
    sig = by_name("uptrend_momentum").evaluate(ctx(df))
    assert sig is not None and abs(sig.stop - (104.0 - 1.5 * 2.0)) < 1e-9


def test_uptrend_momentum_below_vwap_rejected():
    df = frame(ema9=[103.0], ema21=[101.0], ema50=[98.0], macd_hist=[0.1, 0.2, 0.3], rsi14=[62.0],
               close=[104.0], vwap=[105.0])
    assert by_name("uptrend_momentum").evaluate(ctx(df)) is None


# 3. breakout_retest
def test_breakout_retest_positive():
    df = frame(hh24=[101.0, 103.0], close=[103.0, 102.0], rel_vol=[2.5, 1.2], low=[100.5, 101.2], high=[103.5, 102.5])
    sig = by_name("breakout_retest").evaluate(ctx(df))
    assert sig is not None and abs(sig.stop - (101.0 - 0.5 * 2.0)) < 1e-9


def test_breakout_without_volume_rejected():
    df = frame(hh24=[101.0, 103.0], close=[103.0, 102.0], rel_vol=[1.4, 1.2], low=[100.5, 101.2])
    assert by_name("breakout_retest").evaluate(ctx(df)) is None


def test_breakout_lost_level_rejected():
    df = frame(hh24=[101.0, 103.0], close=[103.0, 100.5], rel_vol=[2.5, 1.2], low=[100.5, 100.2])
    assert by_name("breakout_retest").evaluate(ctx(df)) is None


# 4. reversal_confirmed
def _divergence_frame(close_last=97.0, ema9_last=96.5):
    lows = [95.0, 94.0, 95.0, 96.0, 97.0, 96.0, 95.0, 93.5, 94.5, 95.5, 96.0, close_last - 0.5]
    rsis = [35.0, 28.0, 33.0, 38.0, 42.0, 40.0, 37.0, 34.0, 38.0, 42.0, 45.0, 47.0]
    return frame(low=lows, rsi14=rsis, close=[95.5] * 11 + [close_last], bb_low=[93.0] * 12, ema9=[95.0] * 11 + [ema9_last])


def test_reversal_positive():
    sig = by_name("reversal_confirmed").evaluate(ctx(_divergence_frame()))
    assert sig is not None and abs(sig.stop - (93.5 - 0.25 * 2.0)) < 1e-9


def test_reversal_below_ema9_rejected():
    assert by_name("reversal_confirmed").evaluate(ctx(_divergence_frame(close_last=96.0, ema9_last=96.5))) is None


# 5. new_token_momentum
def _new_ctx(classification="A", buys_m5=30, sells_m5=15, launch_open=50.0, price=100.0):
    df = frame(n=30, open=[launch_open] + [100.0] * 29, close=[price] * 30, atr14=[2.0] * 30)
    s = snap(price=price, age=timedelta(hours=3), liq=40_000, buys_m5=buys_m5, sells_m5=sells_m5, buys_h1=240, sells_h1=150)
    return ctx(df, category="new", s=s, classification=classification)


def test_new_token_momentum_positive():
    sig = by_name("new_token_momentum").evaluate(_new_ctx())
    assert sig is not None
    assert abs(sig.stop - 100.0 * (1 - 0.12)) < 1e-9  # máx(12%, 1,5 ATR = 3%)


def test_new_token_momentum_requires_class_A():
    assert by_name("new_token_momentum").evaluate(_new_ctx(classification="B")) is None


def test_new_token_momentum_ratio_out_of_range():
    assert by_name("new_token_momentum").evaluate(_new_ctx(buys_m5=70, sells_m5=10)) is None


def test_new_token_momentum_rejects_over_3x_launch():
    assert by_name("new_token_momentum").evaluate(_new_ctx(launch_open=30.0)) is None


def test_new_token_momentum_only_new():
    df = frame()
    assert "new_token_momentum" not in names(run_strategies(ctx(df, category="established", classification="A")))


# 6. abnormal_volume
def test_abnormal_volume_positive():
    df = frame(rel_vol=[3.5], open=[100.0], close=[101.5], low=[99.8], high=[102.0])
    sig = by_name("abnormal_volume").evaluate(ctx(df))
    assert sig is not None and sig.stop == 99.8


def test_abnormal_volume_run_too_far_rejected():
    df = frame(rel_vol=[3.5], open=[100.0], close=[103.0], low=[99.8], high=[103.0])
    assert by_name("abnormal_volume").evaluate(ctx(df)) is None


def test_abnormal_volume_sellers_dominate_rejected():
    df = frame(rel_vol=[3.5], open=[100.0], close=[101.5], low=[99.8])
    s = snap(price=101.5, buys_m5=10, sells_m5=20)
    assert by_name("abnormal_volume").evaluate(ctx(df, s=s)) is None


def test_flat_market_no_signals():
    assert run_strategies(ctx(frame())) == []


def test_insufficient_candles_skipped():
    assert run_strategies(ctx(frame(n=10))) == []


def test_all_strategies_describe_complete():
    assert len(ALL_STRATEGIES) == 6
    for s in ALL_STRATEGIES:
        d = s.describe()
        assert set(d) >= {"nome", "entrada", "invalidacao", "saida", "horizonte", "indicadores", "limitacoes"}
        assert all(d[k] for k in d)
