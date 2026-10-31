"""Métricas de desempenho. Taxa de acerto sozinha não mede qualidade: expectativa e profit factor vêm junto."""
from collections import defaultdict


def _get(t, key):
    return t[key] if isinstance(t, dict) else getattr(t, key)


def _basic(pnls: list[float], amounts: list[float]) -> dict:
    n = len(pnls)
    if n == 0:
        return {"n": 0, "pnl_usd": 0.0, "win_rate": None, "avg_return_pct": None, "expectancy_usd": None,
                "profit_factor": None, "avg_win_usd": None, "avg_loss_usd": None}
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_loss = -sum(losses)
    return {
        "n": n,
        "pnl_usd": sum(pnls),
        "win_rate": len(wins) / n,
        "avg_return_pct": sum(p / a * 100 for p, a in zip(pnls, amounts)) / n,
        "expectancy_usd": sum(pnls) / n,
        "profit_factor": (sum(wins) / gross_loss) if gross_loss > 0 else float("inf"),
        "avg_win_usd": sum(wins) / len(wins) if wins else None,
        "avg_loss_usd": sum(losses) / len(losses) if losses else None,
    }


def compute_metrics(trades: list) -> dict:
    """trades em ordem cronológica de fechamento; cada um com pnl_usd, amount_usd, strategy, category."""
    pnls = [float(_get(t, "pnl_usd")) for t in trades]
    amounts = [float(_get(t, "amount_usd")) for t in trades]
    out = _basic(pnls, amounts)

    equity = peak = dd = 0.0
    best = worst = cur_w = cur_l = 0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
        if p > 0:
            cur_w, cur_l = cur_w + 1, 0
        else:
            cur_l, cur_w = cur_l + 1, 0
        best, worst = max(best, cur_w), max(worst, cur_l)
    out.update(max_drawdown_usd=dd, best_streak=best, worst_streak=worst)

    for key, field in (("by_strategy", "strategy"), ("by_category", "category")):
        groups: dict[str, list] = defaultdict(list)
        for t in trades:
            groups[_get(t, field) or "manual"].append(t)
        out[key] = {
            g: _basic([float(_get(t, "pnl_usd")) for t in ts], [float(_get(t, "amount_usd")) for t in ts])
            for g, ts in groups.items()
        }
    return out
