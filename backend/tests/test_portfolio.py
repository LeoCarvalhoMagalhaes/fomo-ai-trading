import math
from datetime import timedelta

from app.config import DEFAULT_RUNTIME
from app.db.models import Token
from app.db.session import Database
from app.portfolio.ledger import book_state, close_trade, open_trade
from app.portfolio.metrics import compute_metrics
from app.risk.manager import RiskLimits
from tests.conftest import NOW

LIMITS = RiskLimits.from_settings(DEFAULT_RUNTIME)


def setup():
    db = Database("sqlite:///:memory:")
    with db.session() as s:
        t = Token(chain="solana", address="TOK", symbol="TOK", name="Tok")
        s.add(t)
        s.flush()
        return db, t.id


def test_pnl_with_fees():
    db, tid = setup()
    with db.session() as s:
        tr = open_trade(s, "REAL", tid, 10.0, 1.0, 0.05, NOW, limits=LIMITS, now=NOW, category="established")
        tr = close_trade(s, tr.id, 1.1, 0.05, NOW + timedelta(minutes=40), "alvo1")
    assert abs(tr.pnl_usd - (1.0 - 0.10)) < 1e-9
    assert tr.status == "CLOSED"


def test_ledgers_are_separate():
    db, tid = setup()
    with db.session() as s:
        a = open_trade(s, "SIM", tid, 10.0, 1.0, 0.0, NOW, limits=LIMITS, now=NOW, category="established")
        close_trade(s, a.id, 0.9, 0.0, NOW + timedelta(minutes=10), "stop")
        open_trade(s, "REAL", tid, 5.0, 1.0, 0.0, NOW, limits=LIMITS, now=NOW, category="established")
        sim = book_state(s, "SIM", NOW + timedelta(minutes=11), LIMITS)
        real = book_state(s, "REAL", NOW + timedelta(minutes=11), LIMITS)
    assert abs(sim.realized_pnl + 1.0) < 1e-9 and sim.open_positions == []
    assert real.realized_pnl == 0 and len(real.open_positions) == 1
    assert sim.consecutive_losses == 1 and real.consecutive_losses == 0


def test_manual_trade_over_limit_is_flagged():
    db, tid = setup()
    with db.session() as s:
        tr = open_trade(s, "REAL", tid, 20.0, 1.0, 0.0, NOW, limits=LIMITS, now=NOW, category="established")
    assert tr.status == "OPEN"  # a operação é um fato e fica registrada
    assert any("máximo por operação" in f for f in tr.limit_flags)
    assert any("exposição" in f for f in tr.limit_flags)


def test_book_state_day_pnl_and_streak():
    db, tid = setup()
    with db.session() as s:
        for i, exit_price in enumerate([1.1, 0.95, 0.9]):
            t = open_trade(s, "SIM", tid, 5.0, 1.0, 0.0, NOW + timedelta(minutes=i), limits=LIMITS, now=NOW, category="established")
            close_trade(s, t.id, exit_price, 0.0, NOW + timedelta(minutes=10 + i), "x")
        b = book_state(s, "SIM", NOW + timedelta(hours=1), LIMITS)
    assert b.consecutive_losses == 2
    assert abs(b.day_realized_pnl - (0.5 - 0.25 - 0.5)) < 1e-9
    assert b.last_loss_at == NOW + timedelta(minutes=12)


def _t(pnl, amount=10.0, strategy="s", category="established"):
    return {"pnl_usd": pnl, "amount_usd": amount, "strategy": strategy, "category": category}


def test_drawdown_and_streaks():
    m = compute_metrics([_t(1), _t(1), _t(-0.5), _t(-1), _t(-0.5), _t(2)])
    assert m["n"] == 6
    assert abs(m["win_rate"] - 0.5) < 1e-9
    assert abs(m["max_drawdown_usd"] - 2.0) < 1e-9
    assert m["best_streak"] == 2 and m["worst_streak"] == 3
    assert abs(m["profit_factor"] - 4 / 2) < 1e-9
    assert abs(m["expectancy_usd"] - 2 / 6) < 1e-9


def test_profit_factor_no_losses_is_inf():
    assert math.isinf(compute_metrics([_t(1), _t(2)])["profit_factor"])


def test_metrics_by_strategy_and_category():
    m = compute_metrics([_t(1, strategy="a"), _t(-1, strategy="b", category="new")])
    assert m["by_strategy"]["a"]["n"] == 1 and m["by_category"]["new"]["pnl_usd"] == -1


def test_metrics_empty():
    m = compute_metrics([])
    assert m["n"] == 0 and m["win_rate"] is None
