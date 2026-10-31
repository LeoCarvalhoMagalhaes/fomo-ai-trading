import copy

from app.chains import Chain
from app.providers.goplus import parse_evm, parse_solana
from tests.conftest import NOW, load_fixture

PEPE = "0x6982508145454ce325ddbe47a25d4ec3d2311933"
BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"


def test_parse_evm_pepe():
    r = parse_evm(load_fixture("goplus_eth_pepe.json"), Chain.ethereum, PEPE, NOW)
    assert r.source == "goplus"
    assert r.flags["honeypot"] is False
    assert r.flags["transfer_pausable"] is True
    assert r.flags["blacklist"] is True
    assert r.owner_active is False  # owner 0x000…000 = renunciado
    assert r.taxes["sell"] == 0.0 and r.taxes["buy"] == 0.0
    assert r.flags["open_source"] is True
    assert 30 < r.top10_pct < 40


def test_parse_evm_empty_tax_is_unknown():
    data = copy.deepcopy(load_fixture("goplus_eth_pepe.json"))
    data["result"][PEPE]["sell_tax"] = ""
    data["result"][PEPE]["is_honeypot"] = ""
    r = parse_evm(data, Chain.ethereum, PEPE, NOW)
    assert r.taxes["sell"] is None
    assert r.flags["honeypot"] is None


def test_parse_evm_owner_active():
    data = copy.deepcopy(load_fixture("goplus_eth_pepe.json"))
    data["result"][PEPE]["owner_address"] = "0xabc0000000000000000000000000000000000001"
    assert parse_evm(data, Chain.ethereum, PEPE, NOW).owner_active is True


def test_parse_solana_bonk():
    r = parse_solana(load_fixture("goplus_solana_bonk.json"), Chain.solana, BONK, NOW)
    assert r.flags["freezable"] is False
    assert r.flags["mintable"] is False
    assert r.flags["balance_mutable"] is False
    assert r.flags["non_transferable"] is False
    assert r.flags["transfer_hook"] is False
    assert r.holder_count == 1020153
    assert round(r.top10_pct, 2) == 38.43


def test_parse_missing_result_returns_none():
    empty = {"code": 1, "message": "OK", "result": {}}
    assert parse_evm(empty, Chain.ethereum, PEPE, NOW) is None
    assert parse_solana(empty, Chain.solana, BONK, NOW) is None
