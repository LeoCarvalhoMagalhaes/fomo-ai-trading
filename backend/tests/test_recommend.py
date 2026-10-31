from dataclasses import dataclass
from datetime import datetime, timedelta

from app.chains import Chain
from app.config import DEFAULT_RUNTIME, SCORE_COMPONENTS
from app.costs import estimate_costs
from app.market.manipulation import ManipulationReport
from app.recommend.format import FIELD_ORDER, NO_TRADE_MESSAGE, build_recommendation, render_text
from app.recommend.lifecycle import should_expire
from app.risk.manager import RiskDecision
from app.scoring.engine import score_signal
from app.security.rules import SecurityVerdict
from tests.test_strategies import ctx, frame, snap
from tests.test_scoring import signal
from tests.conftest import NOW

WEIGHTS = {k: DEFAULT_RUNTIME[f"score.weight.{k}"] for k in SCORE_COMPONENTS}


def make_rec():
    c = ctx(frame())
    c.token = {"symbol": "ABC", "name": "Abc", "chain": "solana", "address": "ADDR", "pair_address": "PAIR"}
    sig = signal()
    costs = estimate_costs(Chain.solana, 7, 1_000_000, DEFAULT_RUNTIME)
    sec = SecurityVerdict(penalties=[("Owner não renunciado", 1.0)], coverage=1.0, sources=["goplus"])
    score = score_signal(c, sig, costs, sec, ManipulationReport(), 0.5, 1.0, WEIGHTS)
    decision = RiskDecision("APROVADA", 7.0, ["ok"], costs, 1.8)
    sources = [{"fonte": "dexscreener", "horario": NOW}]
    return build_recommendation(c, sig, score, decision, sec, ManipulationReport(), sources, NOW)


def test_render_has_all_fields_in_order():
    text = render_text(make_rec())
    positions = [text.index(f"{label}:") for label in FIELD_ORDER]
    assert positions == sorted(positions)
    assert "DIREÇÃO: Compra" in text
    assert "VALOR SUGERIDO: US$ 7.00" in text
    assert "CONFIANÇA ESTATÍSTICA: Sem estimativa confiável" in text
    assert "Confirme no app da FOMO" in text
    assert "Owner não renunciado" in text


def test_no_trade_message():
    assert NO_TRADE_MESSAGE == "SEM OPERAÇÃO RECOMENDADA — aguardando condições melhores."


@dataclass
class Rec:
    created_at: datetime
    expires_at: datetime
    price_observed: float
    stop: float


def rec():
    return Rec(created_at=NOW, expires_at=NOW + timedelta(minutes=10), price_observed=100.0, stop=95.0)


def test_active_while_conditions_hold():
    assert should_expire(rec(), snap(price=100.5), NOW + timedelta(minutes=1), []) is None


def test_expires_after_10_min():
    assert "10 min" in should_expire(rec(), snap(price=100.0), NOW + timedelta(minutes=10, seconds=1), [])


def test_expires_when_price_runs_1_5pct():
    assert "subiu" in should_expire(rec(), snap(price=101.6), NOW + timedelta(minutes=1), [])


def test_expires_below_stop():
    assert "stop" in should_expire(rec(), snap(price=94.9), NOW + timedelta(minutes=1), [])


def test_expires_on_stale_data():
    s = snap(price=100.0)
    s.observed_at = NOW - timedelta(minutes=3)
    assert "desatualizados" in should_expire(rec(), s, NOW, [])


def test_expires_on_new_block():
    assert "Honeypot" in should_expire(rec(), snap(price=100.0), NOW, ["Honeypot"])
