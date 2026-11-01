import ast
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from app.chains import Chain
from app.config import DEFAULT_RUNTIME
from app.risk.manager import BookState, OpenPosition, RiskLimits, TradeProposal, evaluate
from tests.conftest import NOW

# Cenário de custo baixo (sem taxa mínima) para testar dimensionamento; o padrão real é testado à parte
LOW_COST = dict(DEFAULT_RUNTIME, **{"cost.fomo_min_fee_usd": 0.0})
LIMITS = RiskLimits.from_settings(LOW_COST)


def proposal(**kw):
    base = dict(chain=Chain.solana, token_address="T", strategy="uptrend_momentum", category="established",
                score=95.0, price=1.0, stop=0.92, target1=1.25, liquidity_usd=2_000_000, data_reliability=1.0, blocks=[])
    base.update(kw)
    return TradeProposal(**base)


def book(**kw):
    base = dict(capital_initial=50.0, realized_pnl=0.0, open_positions=[], day_realized_pnl=0.0,
                consecutive_losses=0, last_loss_at=None, recent_recs=[], paused=False)
    base.update(kw)
    return BookState(**base)


def test_approves_clean_proposal_at_max():
    d = evaluate(proposal(), book(), LIMITS, NOW)
    assert d.status == "APROVADA" and d.amount_usd == 10.0
    assert d.costs is not None


def test_veto_on_blocks():
    d = evaluate(proposal(blocks=["Honeypot"]), book(), LIMITS, NOW)
    assert d.status == "VETADA" and "Honeypot" in d.reasons


def test_veto_score_below_min():
    assert evaluate(proposal(score=79.9), book(), LIMITS, NOW).status == "VETADA"


def test_veto_rr_below_1_5():
    d = evaluate(proposal(target1=1.15), book(), LIMITS, NOW)  # +15% contra -8%, menos custos
    assert d.status == "VETADA" and any("R:R" in r for r in d.reasons)


def test_veto_target_below_2x_cost():
    d = evaluate(proposal(stop=0.995, target1=1.012), book(), LIMITS, NOW)
    assert d.status == "VETADA" and any("custo" in r for r in d.reasons)


def test_veto_stop_tighter_than_2x_cost():
    d = evaluate(proposal(stop=0.92, target1=1.30), book(), LIMITS, NOW)
    assert d.status == "APROVADA"
    d = evaluate(proposal(stop=0.99, target1=1.30), book(), LIMITS, NOW)
    assert d.status == "VETADA" and any("stop" in r.lower() for r in d.reasons)


def test_new_token_capped_at_5():
    d = evaluate(proposal(category="new"), book(), LIMITS, NOW)
    assert d.status == "APROVADA" and d.amount_usd == 5.0


def test_quality_factor_scales_size():
    assert evaluate(proposal(score=80), book(), LIMITS, NOW).amount_usd == 6.0
    assert evaluate(proposal(score=90), book(), LIMITS, NOW).amount_usd == 8.0


def test_exposure_cap_15():
    open_ = [OpenPosition("A", "established", 10.0)]
    d = evaluate(proposal(), book(open_positions=open_), LIMITS, NOW)
    assert d.status == "REDUZIDA" and d.amount_usd == 5.0


def test_new_exposure_cap_5():
    open_ = [OpenPosition("A", "new", 5.0)]
    d = evaluate(proposal(category="new"), book(open_positions=open_), LIMITS, NOW)
    assert d.status == "VETADA"


def test_reserve_30_respected():
    # capital atual 40 (perdeu 10): disponível = 40 - 0 - 30 = 10; com 4 abertos = 6
    d = evaluate(proposal(), book(realized_pnl=-10.0, open_positions=[OpenPosition("A", "established", 4.0)]), LIMITS, NOW)
    assert d.amount_usd == 6.0 and d.status == "REDUZIDA"
    d = evaluate(proposal(), book(realized_pnl=-16.0), LIMITS, NOW)
    assert d.status == "VETADA"


def test_daily_loss_stops():
    d = evaluate(proposal(), book(day_realized_pnl=-2.5), LIMITS, NOW)
    assert d.status == "VETADA" and any("perda diária" in r for r in d.reasons)


def test_three_losses_pause_2h():
    b = book(consecutive_losses=3, last_loss_at=NOW - timedelta(minutes=30))
    assert evaluate(proposal(), b, LIMITS, NOW).status == "VETADA"
    b = book(consecutive_losses=3, last_loss_at=NOW - timedelta(hours=2, minutes=1))
    assert evaluate(proposal(), b, LIMITS, NOW).status != "VETADA"


def test_duplicate_vetoed():
    b = book(recent_recs=[("T", "uptrend_momentum", NOW - timedelta(minutes=20))])
    assert evaluate(proposal(), b, LIMITS, NOW).status == "VETADA"
    b = book(recent_recs=[("T", "uptrend_momentum", NOW - timedelta(minutes=61))])
    assert evaluate(proposal(), b, LIMITS, NOW).status == "APROVADA"


def test_open_position_same_token_vetoed():
    b = book(open_positions=[OpenPosition("T", "established", 5.0)])
    assert evaluate(proposal(), b, LIMITS, NOW).status == "VETADA"


def test_size_reduced_by_liquidity_impact():
    # impacto máx 0,5%: valor ≤ 0,005 × liquidez/2 → liquidez 2.400 permite 6
    d = evaluate(proposal(liquidity_usd=2_400), book(), LIMITS, NOW)
    assert d.amount_usd == 6.0 and d.status == "REDUZIDA"


def test_below_min_after_reduction_vetoed():
    d = evaluate(proposal(liquidity_usd=1_000), book(), LIMITS, NOW)
    assert d.status == "VETADA" and d.amount_usd == 0


def test_no_size_increase_after_loss():
    clean = evaluate(proposal(), book(), LIMITS, NOW).amount_usd
    after = evaluate(proposal(), book(consecutive_losses=1, last_loss_at=NOW - timedelta(minutes=5)), LIMITS, NOW).amount_usd
    assert after < clean


def test_paused_vetoes():
    assert evaluate(proposal(), book(paused=True), LIMITS, NOW).status == "VETADA"


def test_limits_are_configurable():
    lim = replace(LIMITS, max_exposure_usd=8.0)
    assert evaluate(proposal(), book(), lim, NOW).amount_usd == 8.0


def test_risk_module_has_no_strategy_imports():
    for path in (Path(__file__).parents[1] / "app" / "risk").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(("app.strategy", "app.scoring")), path


def test_default_fomo_min_fee_vetoes_small_trades():
    d = evaluate(proposal(), book(), RiskLimits.from_settings(DEFAULT_RUNTIME), NOW)
    assert d.status == "VETADA" and any("custo" in r for r in d.reasons)


def test_reliability_scales_size():
    full = evaluate(proposal(), book(), LIMITS, NOW).amount_usd
    half = evaluate(proposal(data_reliability=0.6), book(), LIMITS, NOW).amount_usd
    assert half == 6.0 and full == 10.0


def test_loss_factor_expires_with_pause_window():
    old_losses = book(consecutive_losses=3, last_loss_at=NOW - timedelta(hours=3))
    assert evaluate(proposal(), old_losses, LIMITS, NOW).amount_usd == evaluate(proposal(), book(), LIMITS, NOW).amount_usd
