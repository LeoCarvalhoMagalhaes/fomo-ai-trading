import copy

import httpx
import respx

from app.chains import Chain
from app.providers.base import ProviderHealth, RateLimiter
from app.providers.dexscreener import DexScreener, best_pair_per_token, parse_tokens
from tests.conftest import NOW, load_fixture

BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"


def test_parse_tokens_bonk():
    snaps = parse_tokens(load_fixture("dexscreener_tokens_bonk.json"), NOW)
    assert len(snaps) == 1
    s = snaps[0]
    assert s.chain == Chain.solana and s.token_address == BONK
    assert isinstance(s.price_usd, float) and s.price_usd > 0
    assert s.liquidity_usd == 295550.21
    assert s.buys["h1"] == 179 and s.sells["h1"] == 58
    assert s.volume["m5"] == 353.71
    assert s.pair_created_at.year == 2022 and s.pair_created_at.month == 12 and s.pair_created_at.day == 25
    assert s.source == "dexscreener" and s.observed_at == NOW


def test_parse_tokens_handles_null_liquidity():
    data = copy.deepcopy(load_fixture("dexscreener_tokens_bonk.json"))
    data[0]["liquidity"] = None
    data[0]["priceUsd"] = None
    del data[0]["pairCreatedAt"]
    s = parse_tokens(data, NOW)[0]
    assert s.liquidity_usd is None and s.price_usd is None and s.pair_created_at is None


def test_parse_tokens_skips_unknown_chain():
    data = copy.deepcopy(load_fixture("dexscreener_tokens_bonk.json"))
    data[0]["chainId"] = "tron"
    assert parse_tokens(data, NOW) == []


def test_best_pair_per_token_picks_highest_liquidity():
    base = load_fixture("dexscreener_tokens_bonk.json")[0]
    low = copy.deepcopy(base)
    low["pairAddress"] = "LOW"
    low["liquidity"]["usd"] = 10.0
    best = best_pair_per_token(parse_tokens([low, base], NOW))
    assert best[BONK].pair_address == base["pairAddress"]


@respx.mock
async def test_tokens_batches_by_30():
    route = respx.get(url__regex=r"https://api\.dexscreener\.com/tokens/v1/solana/.*").mock(
        return_value=httpx.Response(200, json=load_fixture("dexscreener_tokens_bonk.json"))
    )
    async with httpx.AsyncClient() as client:
        dex = DexScreener(client, RateLimiter(6000), ProviderHealth("dexscreener"))
        snaps = await dex.tokens(Chain.solana, [f"A{i}" for i in range(31)])
    assert route.call_count == 2
    assert len(snaps) == 2
