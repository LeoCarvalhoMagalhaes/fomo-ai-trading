from datetime import timedelta

from app.chains import Chain
from app.domain import SecurityReport
from app.market.category import categorize
from app.providers.goplus import parse_evm, parse_solana
from app.security.rules import evaluate_security
from tests.conftest import NOW, load_fixture

PEPE = "0x6982508145454ce325ddbe47a25d4ec3d2311933"
BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"


def pepe():
    return parse_evm(load_fixture("goplus_eth_pepe.json"), Chain.ethereum, PEPE, NOW)


def bonk():
    return parse_solana(load_fixture("goplus_solana_bonk.json"), Chain.solana, BONK, NOW)


def evm(**kw):
    base = pepe().model_copy(deep=True)
    for k, v in kw.items():
        if k == "flags":
            base.flags.update(v)
        elif k == "taxes":
            base.taxes.update(v)
        else:
            setattr(base, k, v)
    return base


def test_pepe_not_blocked_owner_renounced():
    v = evaluate_security([pepe()], "evm", "established")
    assert v.blocks == []
    assert any("renunciado" in p[0] for p in v.penalties)


def test_honeypot_blocks():
    v = evaluate_security([evm(flags={"honeypot": True})], "evm", "established")
    assert any("honeypot" in b.lower() for b in v.blocks)


def test_sell_tax_over_10_blocks():
    v = evaluate_security([evm(taxes={"sell": 12.0})], "evm", "established")
    assert any("venda" in b for b in v.blocks)


def test_owner_active_pausable_blocks():
    v = evaluate_security([evm(owner_active=True)], "evm", "established")
    assert any("pausar" in b for b in v.blocks)


def test_solana_freeze_blocks():
    r = bonk().model_copy(deep=True)
    r.flags["freezable"] = True
    v = evaluate_security([r], "svm", "established")
    assert any("congelar" in b for b in v.blocks)


def test_mint_blocks_new_penalizes_established():
    r = bonk().model_copy(deep=True)
    r.flags["mintable"] = True
    assert any("mint" in b.lower() for b in evaluate_security([r], "svm", "new").blocks)
    est = evaluate_security([r], "svm", "established")
    assert est.blocks == [] and any("mint" in p[0].lower() for p in est.penalties)


def test_new_token_without_security_is_blocked():
    v = evaluate_security([], "evm", "new")
    assert v.blocks and v.coverage == 0
    est = evaluate_security([], "evm", "established")
    assert est.blocks == [] and est.penalties


def test_top10_over_60_blocks_new():
    r = bonk().model_copy(deep=True)
    r.top10_pct = 65.0
    assert any("10 maiores" in b for b in evaluate_security([r], "svm", "new").blocks)


def test_any_source_flag_counts_worst_case():
    gecko = SecurityReport(chain=Chain.solana, token_address=BONK, source="geckoterminal", observed_at=NOW,
                           flags={"freezable": True, "mintable": False, "honeypot": None})
    v = evaluate_security([bonk(), gecko], "svm", "established")
    assert v.blocks and set(v.sources) == {"goplus", "geckoterminal"}


def test_bonk_full_coverage():
    assert evaluate_security([bonk()], "svm", "established").coverage == 1.0


def test_categorize():
    assert categorize(NOW - timedelta(hours=10), 20_000, NOW) == "new"
    assert categorize(NOW - timedelta(days=30), 300_000, NOW) == "established"
    assert categorize(NOW - timedelta(days=30), 100_000, NOW) == "intermediate"
    assert categorize(NOW - timedelta(days=4), 900_000, NOW) == "intermediate"
    assert categorize(None, 900_000, NOW) == "intermediate"
