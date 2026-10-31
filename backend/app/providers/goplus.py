"""Adaptador GoPlus Security (api.gopluslabs.io), plano gratuito sem chave.

EVM: /api/v1/token_security/{chain_id}; Solana (beta): /api/v1/solana/token_security.
Percentuais de holders e taxas vêm como fração (0,05 = 5%) e são convertidos para %.
"""
from datetime import datetime, timezone

import httpx

from app.chains import CHAINS, Chain
from app.domain import SecurityReport
from app.providers.base import ProviderHealth, RateLimiter, fetch_json

BASE_URL = "https://api.gopluslabs.io/api/v1"
NULL_OWNERS = {"", "0x0000000000000000000000000000000000000000", "0x000000000000000000000000000000000000dead"}

# flag normalizado → campo GoPlus EVM
EVM_FLAGS = {
    "honeypot": "is_honeypot",
    "cannot_sell_all": "cannot_sell_all",
    "cannot_buy": "cannot_buy",
    "selfdestruct": "selfdestruct",
    "hidden_owner": "hidden_owner",
    "can_take_back_ownership": "can_take_back_ownership",
    "honeypot_same_creator": "honeypot_with_same_creator",
    "transfer_pausable": "transfer_pausable",
    "blacklist": "is_blacklisted",
    "owner_change_balance": "owner_change_balance",
    "slippage_modifiable": "slippage_modifiable",
    "trading_cooldown": "trading_cooldown",
    "mintable": "is_mintable",
    "open_source": "is_open_source",
    "proxy": "is_proxy",
}


def _flag(v) -> bool | None:
    if v in ("1", 1, True):
        return True
    if v in ("0", 0, False):
        return False
    return None


def _status(v) -> bool | None:
    return _flag(v.get("status")) if isinstance(v, dict) else _flag(v)


def _pct(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v) * 100
    except (TypeError, ValueError):
        return None


def _top10(holders: list | None, exclude: set[str]) -> float | None:
    if not holders:
        return None
    rows = [h for h in holders if (h.get("address") or h.get("account") or "").lower() not in exclude and not h.get("is_locked")]
    return sum(float(h.get("percent") or 0) for h in rows[:10]) * 100


def _result(data: dict, address: str) -> dict | None:
    result = (data or {}).get("result") or {}
    return result.get(address) or result.get(address.lower())


def parse_evm(data: dict, chain: Chain, address: str, observed_at: datetime) -> SecurityReport | None:
    r = _result(data, address)
    if not r:
        return None
    owner = (r.get("owner_address") or "").lower()
    lp = {(h.get("address") or "").lower() for h in r.get("lp_holders") or []}
    return SecurityReport(
        chain=chain,
        token_address=address,
        source="goplus",
        observed_at=observed_at,
        flags={k: _flag(r.get(v)) for k, v in EVM_FLAGS.items()},
        taxes={"buy": _pct(r.get("buy_tax")), "sell": _pct(r.get("sell_tax")), "transfer": _pct(r.get("transfer_tax"))},
        owner_active=None if "owner_address" not in r else owner not in NULL_OWNERS,
        top10_pct=_top10(r.get("holders"), lp | NULL_OWNERS),
        creator_pct=_pct(r.get("creator_percent")),
        holder_count=int(r["holder_count"]) if r.get("holder_count") else None,
        raw={k: r.get(k) for k in ("owner_address", "creator_address", "is_in_dex", "lp_holder_count", "token_name", "token_symbol")},
    )


def _solana_transfer_fee_pct(fee) -> float | None:
    if not fee:
        return 0.0
    rate = (fee.get("current_fee_rate") or {}).get("fee_rate") if isinstance(fee, dict) else None
    try:
        return float(rate) * 100 if rate is not None else None
    except (TypeError, ValueError):
        return None


def parse_solana(data: dict, chain: Chain, address: str, observed_at: datetime) -> SecurityReport | None:
    r = _result(data, address)
    if not r:
        return None
    lp = {(h.get("account") or h.get("address") or "").lower() for h in r.get("lp_holders") or []}
    return SecurityReport(
        chain=chain,
        token_address=address,
        source="goplus",
        observed_at=observed_at,
        flags={
            "mintable": _status(r.get("mintable")),
            "freezable": _status(r.get("freezable")),
            "balance_mutable": _status(r.get("balance_mutable_authority")),
            "non_transferable": _flag(r.get("non_transferable")),
            "transfer_hook": bool(r.get("transfer_hook")) if "transfer_hook" in r else None,
            "closable": _status(r.get("closable")),
        },
        taxes={"transfer": _solana_transfer_fee_pct(r.get("transfer_fee"))},
        owner_active=None,
        top10_pct=_top10(r.get("holders"), lp),
        holder_count=int(r["holder_count"]) if r.get("holder_count") else None,
        raw={"trusted_token": r.get("trusted_token"), "metadata_mutable": r.get("metadata_mutable")},
    )


class GoPlus:
    name = "goplus"

    def __init__(self, client: httpx.AsyncClient, limiter: RateLimiter, health: ProviderHealth):
        self.client = client
        self.limiter = limiter
        self.health = health

    async def token_security(self, chain: Chain, address: str) -> SecurityReport | None:
        now = datetime.now(timezone.utc)
        if CHAINS[chain].family == "svm":
            data = await fetch_json(self.client, f"{BASE_URL}/solana/token_security", {"contract_addresses": address}, self.limiter, self.health)
            return parse_solana(data, chain, address, now)
        data = await fetch_json(self.client, f"{BASE_URL}/token_security/{CHAINS[chain].goplus_id}", {"contract_addresses": address}, self.limiter, self.health)
        return parse_evm(data, chain, address, now)
