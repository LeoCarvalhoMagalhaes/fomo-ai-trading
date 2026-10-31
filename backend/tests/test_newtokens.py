from datetime import timedelta

from app.chains import Chain
from app.domain import PairSnapshot
from app.market.manipulation import ManipulationReport
from app.newtokens.classify import classify_new_token
from app.security.rules import SecurityVerdict
from tests.conftest import NOW

CLEAN = SecurityVerdict(blocks=[], penalties=[], coverage=1.0, sources=["goplus", "geckoterminal"])
NO_MANIP = ManipulationReport(blocks=[], penalties=[], flags={})


def snap(age_min=120, minutes_ago=0, liq=30_000, buyers_m5=12, buyers_h1=60, buys_m5=15, buys_h1=80):
    return PairSnapshot(
        chain=Chain.solana, token_address="T", pair_address="P", symbol="T", name="T",
        price_usd=0.001, liquidity_usd=liq,
        buys={"m5": buys_m5, "h1": buys_h1}, sells={"m5": 8, "h1": 50},
        buyers={"m5": buyers_m5, "h1": buyers_h1}, sellers={"m5": 6, "h1": 40},
        pair_created_at=NOW - timedelta(minutes=age_min), observed_at=NOW - timedelta(minutes=minutes_ago),
        source="geckoterminal",
    )


def history():
    return [snap(minutes_ago=15, liq=29_000), snap(minutes_ago=5, liq=29_500)]


def test_classify_A_when_everything_confirms():
    cls, reasons = classify_new_token(snap(), history(), CLEAN, NO_MANIP, NOW)
    assert cls == "A", reasons


def test_classify_C_on_any_block():
    blocked = SecurityVerdict(blocks=["honeypot"], penalties=[], coverage=1.0, sources=["goplus"])
    assert classify_new_token(snap(), history(), blocked, NO_MANIP, NOW)[0] == "C"
    manip = ManipulationReport(blocks=["pump"], penalties=[], flags={})
    assert classify_new_token(snap(), history(), CLEAN, manip, NOW)[0] == "C"


def test_classify_B_when_too_young():
    cls, reasons = classify_new_token(snap(age_min=20), history(), CLEAN, NO_MANIP, NOW)
    assert cls == "B" and any("30 min" in r for r in reasons)


def test_classify_A_requires_two_sources_or_full_coverage():
    one_partial = SecurityVerdict(blocks=[], penalties=[], coverage=0.6, sources=["goplus"])
    assert classify_new_token(snap(), history(), one_partial, NO_MANIP, NOW)[0] == "B"
    one_full = SecurityVerdict(blocks=[], penalties=[], coverage=1.0, sources=["goplus"])
    assert classify_new_token(snap(), history(), one_full, NO_MANIP, NOW)[0] == "A"


def test_classify_B_when_buyers_slowing():
    # 2 compradores em 5 min contra média de 5 por 5 min na última hora
    cls, reasons = classify_new_token(snap(buyers_m5=2, buyers_h1=60), history(), CLEAN, NO_MANIP, NOW)
    assert cls == "B" and any("compradores" in r for r in reasons)


def test_classify_B_when_liquidity_falling():
    hist = [snap(minutes_ago=15, liq=40_000), snap(minutes_ago=5, liq=35_000)]
    cls, reasons = classify_new_token(snap(liq=30_000), hist, CLEAN, NO_MANIP, NOW)
    assert cls == "B" and any("liquidez" in r for r in reasons)


def test_classify_B_without_history():
    cls, reasons = classify_new_token(snap(), [], CLEAN, NO_MANIP, NOW)
    assert cls == "B" and any("histórico" in r for r in reasons)
