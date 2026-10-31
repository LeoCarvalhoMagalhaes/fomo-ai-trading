"""Tipos de domínio independentes de provedor. Todo dado de mercado carrega horário, origem e confiabilidade."""
from datetime import datetime

from pydantic import BaseModel, Field

from app.chains import Chain


class PairSnapshot(BaseModel):
    chain: Chain
    token_address: str
    pair_address: str
    symbol: str
    name: str
    dex_id: str | None = None
    quote_symbol: str | None = None
    price_usd: float | None
    liquidity_usd: float | None
    volume: dict[str, float] = Field(default_factory=dict)
    buys: dict[str, int] = Field(default_factory=dict)
    sells: dict[str, int] = Field(default_factory=dict)
    buyers: dict[str, int] | None = None
    sellers: dict[str, int] | None = None
    price_change: dict[str, float] = Field(default_factory=dict)
    fdv_usd: float | None = None
    market_cap_usd: float | None = None
    pair_created_at: datetime | None = None
    observed_at: datetime
    source: str
    reliability: float = 1.0


class Candle(BaseModel):
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class SecurityReport(BaseModel):
    chain: Chain
    token_address: str
    source: str
    observed_at: datetime
    # True = sinal de risco presente; False = verificado ausente; None = desconhecido
    flags: dict[str, bool | None] = Field(default_factory=dict)
    taxes: dict[str, float | None] = Field(default_factory=dict)
    owner_active: bool | None = None
    top10_pct: float | None = None
    creator_pct: float | None = None
    holder_count: int | None = None
    raw: dict = Field(default_factory=dict)
