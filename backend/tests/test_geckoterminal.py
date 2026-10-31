import copy

import httpx
import respx

from app.chains import Chain
from app.providers.base import ProviderHealth, RateLimiter
from app.providers.geckoterminal import GeckoTerminal, parse_ohlcv, parse_pools, parse_token_info
from tests.conftest import NOW, load_fixture


def test_parse_pools_new_solana():
    snaps = parse_pools(load_fixture("gecko_new_pools_solana.json"), Chain.solana, NOW)
    assert len(snaps) == 20
    s = snaps[0]
    assert s.token_address == "AvhZFs1AuG5gmecHPCz9nSYV2bzQUMzdQgXvBeqRpump"
    assert s.pair_address == "ARrkKdR5syjXHqHKPCr2raacEYytxzZNsCnJ46vbtriS"
    assert s.symbol == "LARP" and s.quote_symbol == "SOL"
    assert s.buyers["m5"] == 4 and s.sellers["m5"] == 0
    assert s.liquidity_usd == 10.6046
    assert s.pair_created_at.isoformat() == "2026-10-31T13:50:13+00:00"
    assert s.source == "geckoterminal"


def test_parse_pools_null_fields():
    data = copy.deepcopy(load_fixture("gecko_new_pools_solana.json"))
    a = data["data"][0]["attributes"]
    a["reserve_in_usd"] = None
    a["base_token_price_usd"] = None
    a["market_cap_usd"] = None
    a["pool_created_at"] = None
    s = parse_pools(data, Chain.solana, NOW)[0]
    assert s.liquidity_usd is None and s.price_usd is None and s.pair_created_at is None


def test_parse_ohlcv_sorted_ascending():
    candles = parse_ohlcv(load_fixture("gecko_ohlcv_5m.json"))
    assert len(candles) == 41
    assert all(a.ts < b.ts for a, b in zip(candles, candles[1:]))
    assert candles[-1].ts.timestamp() == 1793454600
    assert candles[-1].close == 0.0001187308024389397


def test_parse_token_info_bonk():
    r = parse_token_info(load_fixture("gecko_token_info_bonk.json"), Chain.solana, NOW)
    assert r.source == "geckoterminal"
    assert r.flags["freezable"] is False
    assert r.flags["mintable"] is False
    assert r.flags["honeypot"] is None  # "unknown" não vira "seguro"
    assert r.top10_pct == 38.8358
    assert r.holder_count == 1027178
    assert r.creator_pct == 0.0


@respx.mock
async def test_ohlcv_request_params():
    route = respx.get("https://api.geckoterminal.com/api/v2/networks/eth/pools/P1/ohlcv/minute").mock(
        return_value=httpx.Response(200, json=load_fixture("gecko_ohlcv_5m.json"))
    )
    async with httpx.AsyncClient() as client:
        g = GeckoTerminal(client, RateLimiter(6000), ProviderHealth("geckoterminal"))
        candles = await g.ohlcv(Chain.ethereum, "P1", aggregate=5, limit=100)
    assert len(candles) == 41
    params = route.calls[0].request.url.params
    assert params["aggregate"] == "5" and params["limit"] == "100"
