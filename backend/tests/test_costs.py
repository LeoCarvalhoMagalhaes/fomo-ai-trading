import math

from app.chains import Chain
from app.config import DEFAULT_RUNTIME
from app.costs import estimate_costs


def test_solana_10usd_100k_liquidity():
    c = estimate_costs(Chain.solana, 10, 100_000, DEFAULT_RUNTIME)
    assert abs(c.impact_pct - 0.02) < 1e-9
    # por lado: 1,0 + 0,3 + 0,02 + 0,5 = 1,82%; ida e volta 3,64% + gás 2×0,01/10 = 0,2%
    assert abs(c.round_trip_pct - 3.84) < 1e-9
    assert abs(c.round_trip_usd - 0.384) < 1e-9


def test_ethereum_5usd_gas_dominates():
    c = estimate_costs(Chain.ethereum, 5, 1_000_000, DEFAULT_RUNTIME)
    assert c.round_trip_pct >= 60


def test_none_liquidity_is_infinite_cost():
    c = estimate_costs(Chain.base, 5, None, DEFAULT_RUNTIME)
    assert math.isinf(c.round_trip_pct)


def test_fee_is_configurable():
    cfg = dict(DEFAULT_RUNTIME, **{"cost.fomo_fee_pct": 0.5})
    assert estimate_costs(Chain.solana, 10, 100_000, cfg).round_trip_pct < estimate_costs(Chain.solana, 10, 100_000, DEFAULT_RUNTIME).round_trip_pct
