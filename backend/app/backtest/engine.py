"""Backtest em candles de 5 min com custos completos (spec 5.3).

Limitações declaradas: candles OHLCV não trazem fluxo de compras/vendas, então estratégias que dependem
desse fluxo (abnormal_volume, new_token_momentum) só são avaliadas com os snapshots gravados pelo app.
As regras são fixas (sem otimização de parâmetros); a divisão temporal mostra se o resultado se mantém
fora da amostra.
"""
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from app.chains import Chain
from app.costs import estimate_costs
from app.domain import PairSnapshot
from app.portfolio.metrics import compute_metrics
from app.strategy.base import AnalysisContext


@dataclass
class BTTrade:
    token: str
    strategy: str
    category: str
    entry_ts: datetime
    exit_ts: datetime
    entry: float
    exit: float
    outcome: str
    pnl_pct: float
    amount_usd: float

    @property
    def pnl_usd(self) -> float:
        return self.amount_usd * self.pnl_pct / 100


def time_split(items: list, ratios=(0.6, 0.2, 0.2)) -> tuple[list, list, list]:
    n = len(items)
    a = int(n * ratios[0])
    b = int(n * (ratios[0] + ratios[1]))
    return items[:a], items[a:b], items[b:]


def exit_for(future: pd.DataFrame, stop: float, target: float) -> tuple[str, float, int]:
    """Primeiro evento nos candles seguintes. Alvo e stop no mesmo candle contam como stop (conservador)."""
    for i, (_, bar) in enumerate(future.iterrows()):
        if bar.low <= stop:
            return "stop", stop, i
        if bar.high >= target:
            return "alvo1", target, i
    return "tempo", float(future["close"].iloc[-1]), len(future) - 1


def _snap(token: str, chain: Chain, ts, price: float, liquidity: float) -> PairSnapshot:
    return PairSnapshot(chain=chain, token_address=token, pair_address=token, symbol=token, name=token, price_usd=price,
                        liquidity_usd=liquidity, observed_at=ts.to_pydatetime(), source="backtest")


def simulate(
    df_by_token: dict[str, pd.DataFrame],
    strategies: list,
    cost_cfg: dict,
    chain_of: dict[str, Chain],
    category_of: dict[str, str],
    liquidity_of: dict[str, float],
    max_bars: int = 12,
    amount_usd: float = 10.0,
) -> list[BTTrade]:
    """df_by_token: candles com indicadores já calculados (todos causais)."""
    trades: list[BTTrade] = []
    for token, df in df_by_token.items():
        chain, category, liq = chain_of[token], category_of[token], liquidity_of[token]
        costs = estimate_costs(chain, amount_usd, liq, cost_cfg)
        slip = (costs.slippage_pct + costs.impact_pct) / 100
        fees_pct = 2 * (costs.fomo_fee_pct + costs.pool_fee_pct) + 2 * costs.gas_usd / amount_usd * 100
        usable = [s for s in strategies if category in s.categories]
        i = max((s.min_candles for s in usable), default=len(df)) - 1
        while i < len(df) - 1:
            window = df.iloc[: i + 1]
            ts = df.index[i]
            price = float(df["close"].iloc[i])
            ctx = AnalysisContext(token={"symbol": token}, category=category, df=window,
                                  snap=_snap(token, chain, ts, price, liq), history=[], now=ts.to_pydatetime())
            signal = next((sig for s in usable if len(window) >= s.min_candles and (sig := s.evaluate(ctx))), None)
            if signal is None:
                i += 1
                continue
            future = df.iloc[i + 1: i + 1 + max_bars]
            outcome, exit_price, k = exit_for(future, signal.stop, signal.target1)
            entry = price * (1 + slip)
            net_exit = exit_price * (1 - slip)
            trades.append(BTTrade(token, signal.strategy, category, ts.to_pydatetime(), future.index[k].to_pydatetime(),
                                  entry, net_exit, outcome, (net_exit / entry - 1) * 100 - fees_pct, amount_usd))
            i += k + 2  # sem sobreposição: próxima entrada só depois da saída
    trades.sort(key=lambda t: t.entry_ts)
    return trades


def bt_metrics(trades: list[BTTrade]) -> dict:
    rows = [{"pnl_usd": t.pnl_usd, "amount_usd": t.amount_usd, "strategy": t.strategy, "category": t.category} for t in trades]
    m = compute_metrics(rows)
    m["outcomes"] = {o: sum(1 for t in trades if t.outcome == o) for o in ("alvo1", "stop", "tempo")}
    return m


def split_report(trades: list[BTTrade]) -> dict:
    train, val, test = time_split(trades)
    return {"treino": bt_metrics(train), "validacao": bt_metrics(val), "teste": bt_metrics(test), "total": bt_metrics(trades)}
