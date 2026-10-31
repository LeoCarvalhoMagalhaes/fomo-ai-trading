"""Indicadores técnicos implementados no projeto (sem TA-Lib). RSI e ATR usam a suavização de Wilder."""
import numpy as np
import pandas as pd

from app.domain import Candle


def candles_to_frame(candles: list[Candle]) -> pd.DataFrame:
    df = pd.DataFrame([c.model_dump() for c in candles])
    if df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.set_index("ts").sort_index()[["open", "high", "low", "close", "volume"]].astype(float)


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _wilder(values: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    if len(values) < n:
        return out
    out[n - 1] = values[:n].mean()
    for i in range(n, len(values)):
        out[i] = (out[i - 1] * (n - 1) + values[i]) / n
    return out


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff().to_numpy()[1:]
    gain = _wilder(np.clip(delta, 0, None), n)
    loss = _wilder(np.clip(-delta, 0, None), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = gain / loss
        values = np.where(loss == 0, np.where(gain == 0, 50.0, 100.0), 100 - 100 / (1 + rs))
    values = np.where(np.isnan(gain), np.nan, values)
    return pd.Series(np.concatenate([[np.nan], values]), index=close.index)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return pd.Series(_wilder(tr.to_numpy(), n), index=df.index)


def vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    day = df.index.tz_convert("UTC").normalize() if df.index.tz is not None else df.index.normalize()
    pv = (typical * df["volume"]).groupby(day).cumsum()
    vol = df["volume"].groupby(day).cumsum()
    return (pv / vol.replace(0, np.nan)).rename("vwap")


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c = df["close"]
    for n in (9, 20, 21, 50):
        df[f"ema{n}"] = ema(c, n)
    df["sma20"] = c.rolling(20).mean()
    df["rsi14"] = rsi(c, 14)
    df["macd"] = ema(c, 12) - ema(c, 26)
    df["macd_signal"] = ema(df["macd"], 9)
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    std = c.rolling(20).std(ddof=0)
    df["bb_mid"] = df["sma20"]
    df["bb_up"] = df["sma20"] + 2 * std
    df["bb_low"] = df["sma20"] - 2 * std
    df["atr14"] = atr(df, 14)
    avg_vol = df["volume"].shift(1).rolling(20).mean()
    df["rel_vol"] = df["volume"] / avg_vol.replace(0, np.nan)
    df["hh24"] = df["high"].shift(1).rolling(24).max()
    df["ll24"] = df["low"].shift(1).rolling(24).min()
    df["vwap"] = vwap(df)
    return df


def rsi_bullish_divergence(df: pd.DataFrame, lookback: int = 12, min_gap: int = 3) -> int | None:
    """Posição (iloc) da mínima mais recente de uma divergência de alta: preço faz mínima menor e o RSI, mínima maior."""
    n = len(df)
    if n < lookback + 2:
        return None
    lows = df["low"].to_numpy()
    r = df["rsi14"].to_numpy()
    start = n - lookback
    pivots = [i for i in range(max(start, 1), n - 1) if lows[i] <= lows[i - 1] and lows[i] <= lows[i + 1] and not np.isnan(r[i])]
    if len(pivots) < 2:
        return None
    second = min(pivots[-3:] if len(pivots) >= 3 else pivots, key=lambda i: lows[i])
    earlier = [i for i in pivots if i <= second - min_gap]
    if not earlier:
        return None
    first = min(earlier, key=lambda i: r[i])
    if lows[second] < lows[first] and r[second] > r[first] + 2:
        return second
    return None
