from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.domain import Candle
from app.strategy.indicators import add_indicators, atr, candles_to_frame, ema, rsi, rsi_bullish_divergence, vwap

# Exemplo clássico do RSI de Wilder (tabela publicada pela StockCharts: primeiro RSI(14) = 70,53)
WILDER = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]


def series(values):
    return pd.Series(values, dtype=float)


def test_rsi_wilder_reference():
    r = rsi(series(WILDER), 14)
    assert np.isnan(r.iloc[13])
    assert abs(r.iloc[14] - 70.53) < 0.5


def test_rsi_all_up_is_100():
    r = rsi(series(range(1, 30)), 14)
    assert r.iloc[-1] == 100


def test_ema_constant_series():
    e = ema(series([5.0] * 30), 9)
    assert abs(e.iloc[-1] - 5.0) < 1e-12


def test_atr_constant_range():
    n = 30
    df = pd.DataFrame({"high": [11.0] * n, "low": [9.0] * n, "close": [10.0] * n})
    assert abs(atr(df, 14).iloc[-1] - 2.0) < 1e-12


def test_vwap_resets_daily():
    idx = pd.to_datetime(["2026-10-30T23:50Z", "2026-10-30T23:55Z", "2026-10-31T00:00Z"])
    df = pd.DataFrame({"high": [10, 20, 30], "low": [10, 20, 30], "close": [10, 20, 30], "volume": [1, 1, 5]}, index=idx, dtype=float)
    v = vwap(df)
    assert v.iloc[1] == 15
    assert v.iloc[2] == 30  # novo dia UTC


def _frame(closes, lows=None):
    t0 = datetime(2026, 10, 31, tzinfo=timezone.utc)
    lows = lows or [c * 0.99 for c in closes]
    return candles_to_frame([
        Candle(ts=t0 + timedelta(minutes=5 * i), open=c, high=c * 1.01, low=lo, close=c, volume=100)
        for i, (c, lo) in enumerate(zip(closes, lows))
    ])


def test_add_indicators_columns():
    df = add_indicators(_frame([10 + i * 0.1 for i in range(80)]))
    for col in ("ema9", "ema20", "ema21", "ema50", "sma20", "rsi14", "macd", "macd_signal", "macd_hist",
                "bb_mid", "bb_up", "bb_low", "atr14", "rel_vol", "hh24", "ll24", "vwap"):
        assert col in df.columns
    assert df["ema9"].iloc[-1] > df["ema50"].iloc[-1]


def test_divergence_detected():
    # Série sintética: queda forte até 80, repique, nova mínima um pouco menor (79) com queda bem mais fraca
    closes = [100 - i * 1.0 for i in range(20)]           # 100 → 81
    closes += [80, 84, 88, 90, 89, 87, 85, 83, 81, 80.5, 79.5, 79, 81, 83]
    lows = [c - 0.2 for c in closes]
    df = add_indicators(_frame(closes, lows))
    pos = rsi_bullish_divergence(df, lookback=16)
    assert pos is not None
    assert df["low"].iloc[pos] == min(lows[-16:])


def test_no_divergence_in_steady_fall():
    closes = [100 - i for i in range(40)]
    df = add_indicators(_frame(closes))
    assert rsi_bullish_divergence(df, lookback=12) is None
