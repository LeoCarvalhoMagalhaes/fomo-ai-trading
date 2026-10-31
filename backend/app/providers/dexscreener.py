"""Adaptador DexScreener (api.dexscreener.com). Termos: docs.dexscreener.com/api/api-terms-and-conditions.

Uso pessoal e local; os dados não são repassados a terceiros. Não há candles nesta API.
"""
import logging
from datetime import datetime, timezone

import httpx

from app.chains import CHAINS, Chain, chain_from_dex
from app.domain import PairSnapshot
from app.providers.base import ProviderHealth, RateLimiter, fetch_json

log = logging.getLogger(__name__)
BASE_URL = "https://api.dexscreener.com"
BATCH = 30


def _num(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_pair(p: dict, observed_at: datetime) -> PairSnapshot | None:
    chain = chain_from_dex(p.get("chainId", ""))
    if chain is None:
        return None
    txns = p.get("txns") or {}
    created = p.get("pairCreatedAt")
    liq = p.get("liquidity") or {}
    return PairSnapshot(
        chain=chain,
        token_address=p["baseToken"]["address"],
        pair_address=p["pairAddress"],
        symbol=p["baseToken"].get("symbol") or "",
        name=p["baseToken"].get("name") or "",
        dex_id=p.get("dexId"),
        quote_symbol=(p.get("quoteToken") or {}).get("symbol"),
        price_usd=_num(p.get("priceUsd")),
        liquidity_usd=_num(liq.get("usd")),
        volume={k: float(v) for k, v in (p.get("volume") or {}).items() if v is not None},
        buys={k: int(v.get("buys", 0)) for k, v in txns.items()},
        sells={k: int(v.get("sells", 0)) for k, v in txns.items()},
        price_change={k: float(v) for k, v in (p.get("priceChange") or {}).items() if v is not None},
        fdv_usd=_num(p.get("fdv")),
        market_cap_usd=_num(p.get("marketCap")),
        pair_created_at=datetime.fromtimestamp(created / 1000, tz=timezone.utc) if created else None,
        observed_at=observed_at,
        source="dexscreener",
    )


def parse_tokens(data: list, observed_at: datetime) -> list[PairSnapshot]:
    out = []
    for p in data or []:
        try:
            snap = _parse_pair(p, observed_at)
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("par da DexScreener descartado: %s", exc)
            continue
        if snap is not None:
            out.append(snap)
    return out


def best_pair_per_token(snaps: list[PairSnapshot]) -> dict[str, PairSnapshot]:
    best: dict[str, PairSnapshot] = {}
    for s in snaps:
        cur = best.get(s.token_address)
        if cur is None or (s.liquidity_usd or 0) > (cur.liquidity_usd or 0):
            best[s.token_address] = s
    return best


class DexScreener:
    name = "dexscreener"

    def __init__(self, client: httpx.AsyncClient, limiter: RateLimiter, health: ProviderHealth):
        self.client = client
        self.limiter = limiter
        self.health = health

    async def tokens(self, chain: Chain, addresses: list[str]) -> list[PairSnapshot]:
        out: list[PairSnapshot] = []
        dex_id = CHAINS[chain].dex_id
        for i in range(0, len(addresses), BATCH):
            chunk = ",".join(addresses[i:i + BATCH])
            data = await fetch_json(self.client, f"{BASE_URL}/tokens/v1/{dex_id}/{chunk}", None, self.limiter, self.health)
            out.extend(parse_tokens(data, datetime.now(timezone.utc)))
        return out
