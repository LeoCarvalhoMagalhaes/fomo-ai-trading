import math

from app.chains import Chain
from app.config import DEFAULT_RUNTIME
from app.costs import estimate_costs

NO_MIN = dict(DEFAULT_RUNTIME, **{"cost.fomo_min_fee_usd": 0.0})


def test_default_fee_is_half_percent_with_min():
    assert DEFAULT_RUNTIME["cost.fomo_fee_pct"] == 0.5
    assert DEFAULT_RUNTIME["cost.fomo_min_fee_usd"] == 0.5


def test_solana_10usd_100k_liquidity_with_min_fee():
    c = estimate_costs(Chain.solana, 10, 100_000, DEFAULT_RUNTIME)
    assert abs(c.impact_pct - 0.02) < 1e-9
    # taxa FOMO por lado = máx(0,5% × 10, 0,50) = US$ 0,50 = 5%
    assert abs(c.fomo_fee_pct - 5.0) < 1e-9
    # por lado: 5 + 0,3 + 0,02 + 0,5 = 5,82%; ida e volta 11,64% + gás 0,2%
    assert abs(c.round_trip_pct - 11.84) < 1e-9
    assert abs(c.round_trip_usd - 1.184) < 1e-9


def test_without_min_fee_percent_applies():
    c = estimate_costs(Chain.solana, 10, 100_000, NO_MIN)
    # por lado: 0,5 + 0,3 + 0,02 + 0,5 = 1,32%; ida e volta 2,64% + 0,2%
    assert abs(c.round_trip_pct - 2.84) < 1e-9


def test_ethereum_5usd_gas_dominates():
    c = estimate_costs(Chain.ethereum, 5, 1_000_000, NO_MIN)
    assert c.round_trip_pct >= 60


def test_none_liquidity_is_infinite_cost():
    c = estimate_costs(Chain.base, 5, None, DEFAULT_RUNTIME)
    assert math.isinf(c.round_trip_pct)


def test_fee_is_configurable():
    cheaper = dict(NO_MIN, **{"cost.fomo_fee_pct": 0.25})
    assert estimate_costs(Chain.solana, 10, 100_000, cheaper).round_trip_pct < estimate_costs(Chain.solana, 10, 100_000, NO_MIN).round_trip_pct
