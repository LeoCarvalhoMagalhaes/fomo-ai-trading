"""Adaptador da API pública do GeckoTerminal (api.geckoterminal.com/api/v2), ~10 chamadas/min sem chave.

Fonte de descoberta (pools novos e em alta), candles OHLCV e dados de segurança/holders por token.
"""
import logging
from datetime import datetime, timezone

import httpx

from app.chains import CHAINS, Chain
from app.domain import Candle, PairSnapshot, SecurityReport
from app.providers.base import ProviderHealth, RateLimiter, fetch_json

log = logging.getLogger(__name__)
BASE_URL = "https://api.geckoterminal.com/api/v2"
HEADERS = {"Accept": "application/json;version=20230302"}


def _num(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _strip_network(rel_id: str, gecko_id: str) -> str:
    prefix = f"{gecko_id}_"
    return rel_id[len(prefix):] if rel_id.startswith(prefix) else rel_id.split("_", 1)[-1]


def _parse_dt(v: str | None) -> datetime | None:
    if not v:
        return None
    return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc)


def _yes_no(v) -> bool | None:
    if v in ("yes", True):
        return True
    if v in ("no", False):
        return False
    return None


def _parse_pool(item: dict, chain: Chain, observed_at: datetime) -> PairSnapshot:
    a = item["attributes"]
    rel = item.get("relationships") or {}
    gecko_id = CHAINS[chain].gecko_id
    base_id = rel["base_token"]["data"]["id"]
    name = a.get("name") or ""
    parts = [p.strip() for p in name.split("/")]
    tx = a.get("transactions") or {}
    return PairSnapshot(
        chain=chain,
        token_address=_strip_network(base_id, gecko_id),
        pair_address=a["address"],
        symbol=parts[0] if parts else "",
        name=parts[0] if parts else "",
        dex_id=((rel.get("dex") or {}).get("data") or {}).get("id"),
        quote_symbol=parts[1] if len(parts) > 1 else None,
        price_usd=_num(a.get("base_token_price_usd")),
        liquidity_usd=_num(a.get("reserve_in_usd")),
        volume={k: float(v) for k, v in (a.get("volume_usd") or {}).items() if v is not None},
        buys={k: int(v.get("buys") or 0) for k, v in tx.items()},
        sells={k: int(v.get("sells") or 0) for k, v in tx.items()},
        buyers={k: int(v.get("buyers") or 0) for k, v in tx.items()},
        sellers={k: int(v.get("sellers") or 0) for k, v in tx.items()},
        price_change={k: float(v) for k, v in (a.get("price_change_percentage") or {}).items() if v is not None},
        fdv_usd=_num(a.get("fdv_usd")),
        market_cap_usd=_num(a.get("market_cap_usd")),
        pair_created_at=_parse_dt(a.get("pool_created_at")),
        observed_at=observed_at,
        source="geckoterminal",
    )


def parse_pools(data: dict, chain: Chain, observed_at: datetime) -> list[PairSnapshot]:
    out = []
    for item in (data or {}).get("data") or []:
        try:
            out.append(_parse_pool(item, chain, observed_at))
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("pool do GeckoTerminal descartado: %s", exc)
    return out


def parse_ohlcv(data: dict) -> list[Candle]:
    rows = (((data or {}).get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []
    candles = []
    for r in rows:
        try:
            ts, o, h, l, c, v = r
            candles.append(Candle(ts=datetime.fromtimestamp(ts, tz=timezone.utc), open=o, high=h, low=l, close=c, volume=v or 0.0))
        except (TypeError, ValueError):
            continue
    candles.sort(key=lambda c: c.ts)
    return candles


def parse_token_info(data: dict, chain: Chain, observed_at: datetime) -> SecurityReport | None:
    a = ((data or {}).get("data") or {}).get("attributes")
    if not a:
        return None
    holders = a.get("holders") or {}
    dist = holders.get("distribution_percentage") or {}
    return SecurityReport(
        chain=chain,
        token_address=a.get("address") or "",
        source="geckoterminal",
        observed_at=observed_at,
        flags={
            "mintable": _yes_no(a.get("mint_authority")),
            "freezable": _yes_no(a.get("freeze_authority")),
            "honeypot": _yes_no(a.get("is_honeypot")),
        },
        top10_pct=_num(dist.get("top_10")),
        creator_pct=_num(a.get("developer_holding_percentage")),
        holder_count=holders.get("count"),
        raw={"gt_score": a.get("gt_score"), "gt_verified": a.get("gt_verified"),
             "holders_last_updated": holders.get("last_updated"), "holders_beta": True},
    )


class GeckoTerminal:
    name = "geckoterminal"

    def __init__(self, client: httpx.AsyncClient, limiter: RateLimiter, health: ProviderHealth, demo_key: str | None = None):
        self.client = client
        self.limiter = limiter
        self.health = health
        self.headers = dict(HEADERS)
        if demo_key:
            self.headers["x-cg-demo-api-key"] = demo_key

    async def _get(self, path: str, params: dict | None = None):
        return await fetch_json(self.client, f"{BASE_URL}{path}", params, self.limiter, self.health, self.headers)

    async def new_pools(self, chain: Chain) -> list[PairSnapshot]:
        data = await self._get(f"/networks/{CHAINS[chain].gecko_id}/new_pools", {"page": 1})
        return parse_pools(data, chain, datetime.now(timezone.utc))

    async def trending_pools(self, chain: Chain, duration: str = "1h") -> list[PairSnapshot]:
        data = await self._get(f"/networks/{CHAINS[chain].gecko_id}/trending_pools", {"page": 1, "duration": duration})
        return parse_pools(data, chain, datetime.now(timezone.utc))

    async def ohlcv(self, chain: Chain, pool: str, aggregate: int = 5, limit: int = 100) -> list[Candle]:
        data = await self._get(
            f"/networks/{CHAINS[chain].gecko_id}/pools/{pool}/ohlcv/minute",
            {"aggregate": aggregate, "limit": limit, "currency": "usd"},
        )
        return parse_ohlcv(data)

    async def token_info(self, chain: Chain, address: str) -> SecurityReport | None:
        data = await self._get(f"/networks/{CHAINS[chain].gecko_id}/tokens/{address}/info")
        return parse_token_info(data, chain, datetime.now(timezone.utc))
