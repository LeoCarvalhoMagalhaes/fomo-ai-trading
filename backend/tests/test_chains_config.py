from app.chains import CHAINS, Chain
from app.config import DEFAULT_RUNTIME


def test_chain_ids_match_spec():
    assert set(Chain) == {Chain.solana, Chain.base, Chain.bsc, Chain.ethereum, Chain.monad, Chain.robinhood}
    eth = CHAINS[Chain.ethereum]
    assert (eth.gecko_id, eth.dex_id, eth.goplus_id, eth.family) == ("eth", "ethereum", "1", "evm")
    rh = CHAINS[Chain.robinhood]
    assert (rh.gecko_id, rh.dex_id, rh.goplus_id) == ("robinhood", "robinhood", "4663")
    assert CHAINS[Chain.monad].goplus_id == "143"
    assert CHAINS[Chain.solana].family == "svm"
    assert CHAINS[Chain.ethereum].default_gas_usd == 1.50


def test_default_risk_limits():
    d = DEFAULT_RUNTIME
    assert d["risk.capital_usd"] == 50
    assert (d["risk.established_min_usd"], d["risk.established_max_usd"]) == (5, 10)
    assert d["risk.new_max_usd"] == 5
    assert d["risk.max_exposure_usd"] == 15
    assert d["risk.max_new_exposure_usd"] == 5
    assert d["risk.min_reserve_usd"] == 30
    assert d["risk.max_daily_loss_usd"] == 2.5
    assert d["risk.loss_streak_pause"] == 3
    assert d["risk.loss_streak_pause_hours"] == 2
    assert d["rec.min_score"] == 80
    assert d["rec.min_net_rr"] == 1.5
    assert d["rec.min_target_cost_multiple"] == 2
    assert d["data.max_price_age_s"] == 120
