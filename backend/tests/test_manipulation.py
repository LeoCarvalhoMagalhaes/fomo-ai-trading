from datetime import timedelta

from app.chains import Chain
from app.domain import PairSnapshot
from app.market.manipulation import detect_manipulation
from app.market.reliability import is_stale, reliability
from tests.conftest import NOW


def snap(liq=500_000, vol24=1_000_000, vol_m5=5_000, ch_h1=2.0, ch_h24=5.0, buys_m5=20, sells_m5=15,
         buys_h24=3000, sells_h24=2500, minutes_ago=0):
    return PairSnapshot(
        chain=Chain.base, token_address="T", pair_address="P", symbol="T", name="T", price_usd=1.0,
        liquidity_usd=liq, volume={"m5": vol_m5, "h24": vol24},
        buys={"m5": buys_m5, "h24": buys_h24}, sells={"m5": sells_m5, "h24": sells_h24},
        price_change={"h1": ch_h1, "h24": ch_h24}, observed_at=NOW - timedelta(minutes=minutes_ago),
        source="dexscreener",
    )


def test_clean_market_has_no_blocks():
    r = detect_manipulation(snap(), [], "established")
    assert r.blocks == [] and r.penalties == []


def test_pump_over_300_blocks():
    assert detect_manipulation(snap(ch_h1=350), [], "established").blocks
    r = detect_manipulation(snap(ch_h1=150), [], "established")
    assert r.blocks == [] and r.flags["pump"]


def test_wash_ratio_80x_blocks():
    assert detect_manipulation(snap(liq=100_000, vol24=9_000_000), [], "established").blocks
    r = detect_manipulation(snap(liq=100_000, vol24=4_000_000), [], "established")
    assert r.blocks == [] and r.flags["wash_suspeito"]


def test_wash_balanced_flow_flagged():
    r = detect_manipulation(snap(liq=100_000, vol24=1_500_000, ch_h24=0.5, buys_h24=1000, sells_h24=1010), [], "established")
    assert r.flags["wash_suspeito"]


def test_low_liquidity_blocks_established_under_50k():
    assert detect_manipulation(snap(liq=40_000, vol24=100_000), [], "established").blocks
    assert not detect_manipulation(snap(liq=40_000, vol24=100_000, vol_m5=500), [], "new").blocks
    assert detect_manipulation(snap(liq=10_000, vol24=50_000, vol_m5=500), [], "new").blocks


def test_unknown_liquidity_blocks():
    assert detect_manipulation(snap(liq=None), [], "established").blocks


def test_liquidity_drop_30pct_blocks():
    hist = [snap(liq=800_000, minutes_ago=14), snap(liq=700_000, minutes_ago=7)]
    assert any("liquidez" in b.lower() for b in detect_manipulation(snap(liq=500_000), hist, "established").blocks)


def test_buy_sell_ratio_over_6_flags():
    r = detect_manipulation(snap(buys_m5=70, sells_m5=10), [], "established")
    assert r.flags["pressao_artificial"]


def test_volume_m5_over_half_liquidity_flags():
    r = detect_manipulation(snap(liq=100_000, vol24=500_000, vol_m5=60_000), [], "established")
    assert r.flags["volume_incompativel"]


def test_reliability_divergence_penalty():
    s = snap()
    assert reliability(s, 1.025, NOW) == 0.6
    assert reliability(s, 1.01, NOW) == 1.0
    assert reliability(s, None, NOW) == 1.0


def test_reliability_decays_with_age():
    s = snap(minutes_ago=1)
    assert 0.5 < reliability(s, None, NOW) < 1.0


def test_stale_after_120s():
    assert not is_stale(snap(), NOW + timedelta(seconds=119))
    assert is_stale(snap(), NOW + timedelta(seconds=121))
