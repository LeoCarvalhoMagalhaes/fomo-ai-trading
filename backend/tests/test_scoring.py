from app.chains import Chain
from app.config import DEFAULT_RUNTIME, SCORE_COMPONENTS
from app.costs import estimate_costs
from app.market.manipulation import ManipulationReport
from app.scoring.engine import band, net_rr, score_signal
from app.security.rules import SecurityVerdict
from app.strategy.base import Signal
from tests.test_strategies import ctx, frame

WEIGHTS = {k: DEFAULT_RUNTIME[f"score.weight.{k}"] for k in SCORE_COMPONENTS}


def signal(price=100.0, stop=95.0):
    r = price - stop
    return Signal("uptrend_momentum", price, price * 0.995, price * 1.01, stop, price + 1.5 * r, price + 2.5 * r, "c", "i", ["x"])


def costs():
    return estimate_costs(Chain.solana, 10, 1_000_000, DEFAULT_RUNTIME)


def run(weights=WEIGHTS, **kw):
    df = frame(ema9=[103.0], ema21=[101.0], ema50=[98.0], macd_hist=[0.1, 0.2, 0.3], rsi14=[62.0], close=[100.0], rel_vol=[2.5])
    return score_signal(ctx(df), signal(), costs(), SecurityVerdict(coverage=1.0, sources=["goplus"]),
                        ManipulationReport(), market_regime=kw.get("regime", 0.6), data_reliability=kw.get("rel", 1.0), weights=weights)


def test_total_is_weighted_mean_times_10():
    res = run()
    assert len(res.components) == 10
    expected = sum(c.value * c.weight for c in res.components) / sum(c.weight for c in res.components) * 10
    assert abs(res.total - expected) < 1e-9
    assert 0 <= res.total <= 100


def test_weights_change_total():
    heavy = dict(WEIGHTS, condicoes_mercado=5.0)
    assert run(weights=heavy, regime=0.0).total < run(regime=0.0).total


def test_bands():
    assert band(95) == "alta_prioridade"
    assert band(90) == "alta_prioridade"
    assert band(85) == "interessante"
    assert band(72) == "acompanhar"
    assert band(69.9) == "sem_recomendacao"


def test_net_rr_includes_costs():
    c = costs()
    s = signal()  # alvo 1 = +7,5%, stop = -5%
    expected = (7.5 - c.round_trip_pct) / (5 + c.round_trip_pct)
    assert abs(net_rr(s, c) - expected) < 1e-9
    assert net_rr(s, c) < 1.5  # sem custos seria 1,5


def test_each_component_has_reason():
    for comp in run().components:
        assert comp.reason and 0 <= comp.value <= 10


def test_security_penalties_lower_component():
    df = frame()
    bad = SecurityVerdict(penalties=[("Owner ativo", 1.0), ("Mint ativo", 2.0)], coverage=1.0, sources=["goplus"])
    good = SecurityVerdict(coverage=1.0, sources=["goplus"])
    sb = score_signal(ctx(df), signal(), costs(), bad, ManipulationReport(), 0.5, 1.0, WEIGHTS)
    sg = score_signal(ctx(df), signal(), costs(), good, ManipulationReport(), 0.5, 1.0, WEIGHTS)
    get = lambda r: next(c for c in r.components if c.name == "seguranca_contrato").value
    assert get(sb) == get(sg) - 3
