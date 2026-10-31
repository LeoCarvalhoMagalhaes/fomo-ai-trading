"""Coleta e armazenamento de dados de mercado em dois níveis (spec 2).

Nível 1: tokens descobertos (pools novos e em alta) atualizados pela DexScreener em lote.
Nível 2: até N ativos pré-selecionados recebem candles de 5 min e checagem de segurança.
Todo dado gravado carrega horário, origem e confiabilidade.
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import select

from app.chains import Chain
from app.db.models import Candle as CandleRow, Event, SecurityReportRow, Snapshot, Token
from app.db.runtime_settings import RuntimeSettings
from app.db.session import Database
from app.domain import Candle, PairSnapshot, SecurityReport
from app.market.category import categorize
from app.providers.base import ProviderError
from app.providers.dexscreener import best_pair_per_token
from app.strategy.indicators import candles_to_frame

log = logging.getLogger(__name__)

TIER1_WINDOW = timedelta(hours=6)
TIER1_MAX = 240
CANDLE_REFRESH = timedelta(minutes=4)
SECURITY_MAX_AGE = timedelta(minutes=30)
FRESH_FOR_TIER2 = timedelta(minutes=5)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MarketService:
    def __init__(self, db: Database, dex, gecko, goplus, runtime: RuntimeSettings):
        self.db = db
        self.dex = dex
        self.gecko = gecko
        self.goplus = goplus
        self.runtime = runtime
        self.last_discovery: datetime | None = None
        self.last_tier1: datetime | None = None
        self._last_fresh: datetime | None = None
        self._candles_at: dict[int, datetime] = {}
        self.tier_counts = {"nivel1": 0, "nivel2": 0}

    # ---------- diagnóstico ----------
    def health_list(self):
        return [self.dex.health, self.gecko.health, self.goplus.health]

    def provider_status(self, now: datetime | None = None) -> list[dict]:
        now = now or utcnow()
        return [h.as_dict(now) for h in self.health_list()]

    def data_blocked(self, now: datetime) -> str | None:
        max_age = timedelta(seconds=int(self.runtime.get("data.max_price_age_s")))
        if not self.dex.health.ok and not self.gecko.health.ok:
            return "DexScreener e GeckoTerminal indisponíveis"
        if self._last_fresh is None or now - self._last_fresh > max_age:
            return "Nenhum preço atualizado dentro do limite de idade"
        return None

    def log_event(self, level: str, kind: str, message: str, data: dict | None = None) -> None:
        with self.db.session() as s:
            s.add(Event(level=level, kind=kind, message=message, data=data))
        getattr(log, "warning" if level in ("warn", "error") else "info")("%s: %s", kind, message)

    # ---------- armazenamento ----------
    def _upsert_token(self, s, snap: PairSnapshot, via: str | None, now: datetime) -> Token:
        tok = s.scalars(select(Token).where(Token.chain == snap.chain.value, Token.address == snap.token_address)).first()
        if tok is None:
            tok = Token(chain=snap.chain.value, address=snap.token_address, symbol=snap.symbol[:64], name=snap.name[:128],
                        discovered_via=via, first_seen=now)
            s.add(tok)
        if snap.symbol and not tok.symbol:
            tok.symbol = snap.symbol[:64]
        if snap.name and (not tok.name or tok.name == tok.symbol):
            tok.name = snap.name[:128]
        tok.pair_address = snap.pair_address
        tok.dex_id = snap.dex_id or tok.dex_id
        if snap.pair_created_at:
            tok.pair_created_at = snap.pair_created_at
        tok.category = categorize(tok.pair_created_at, snap.liquidity_usd, now)
        tok.last_seen = now
        tok.active = True
        s.flush()
        return tok

    def _store_snapshot(self, s, token_id: int, snap: PairSnapshot) -> None:
        s.add(Snapshot(token_id=token_id, observed_at=snap.observed_at, source=snap.source, price_usd=snap.price_usd,
                       liquidity_usd=snap.liquidity_usd, reliability=snap.reliability, data=snap.model_dump(mode="json")))

    def _store_many(self, snaps: list[PairSnapshot], via: str) -> None:
        now = utcnow()
        with self.db.session() as s:
            for snap in snaps:
                tok = self._upsert_token(s, snap, via, now)
                self._store_snapshot(s, tok.id, snap)

    # ---------- coleta ----------
    async def discover(self, trending: bool = True) -> int:
        found = 0
        for chain in Chain:
            calls = [("new_pools", self.gecko.new_pools)]
            if trending:
                calls.append(("trending", self.gecko.trending_pools))
            for via, fn in calls:
                try:
                    snaps = await fn(chain)
                except ProviderError as exc:
                    self.log_event("warn", "coleta", f"GeckoTerminal {via} {chain.value}: {exc.message}")
                    continue
                self._store_many(snaps, via)
                found += len(snaps)
        self.last_discovery = utcnow()
        return found

    async def refresh_tier1(self) -> int:
        now = utcnow()
        with self.db.session() as s:
            rows = s.execute(
                select(Token.chain, Token.address)
                .where(Token.active.is_(True), Token.last_seen >= now - TIER1_WINDOW, Token.classification.is_not("C"))
                .order_by(Token.last_seen.desc())
                .limit(TIER1_MAX)
            ).all()
            open_rows = s.execute(select(Token.chain, Token.address).where(Token.id.in_(self._held_token_ids(s)))).all()
        by_chain: dict[str, set[str]] = defaultdict(set)
        for chain, addr in [*rows, *open_rows]:
            by_chain[chain].add(addr)
        updated = 0
        for chain, addrs in by_chain.items():
            try:
                snaps = await self.dex.tokens(Chain(chain), sorted(addrs))
            except ProviderError as exc:
                self.log_event("warn", "coleta", f"DexScreener {chain}: {exc.message}")
                continue
            best = best_pair_per_token(snaps)
            self._store_many(list(best.values()), "dexscreener")
            updated += len(best)
        if updated:
            self._last_fresh = utcnow()
        self.last_tier1 = utcnow()
        self.tier_counts["nivel1"] = updated
        return updated

    def _held_token_ids(self, s) -> list[int]:
        from app.db.models import Recommendation, Trade

        ids = set(s.scalars(select(Trade.token_id).where(Trade.status == "OPEN")))
        ids |= set(s.scalars(select(Recommendation.token_id).where(Recommendation.status == "ATIVA")))
        return list(ids)

    def tier2_tokens(self, now: datetime | None = None) -> list[Token]:
        now = now or utcnow()
        cfg = self.runtime.all()
        limit = int(cfg["data.tier2_max_assets"])
        min_liq = {"established": cfg["market.min_liquidity_established"], "intermediate": cfg["market.min_liquidity_established"],
                   "new": cfg["market.min_liquidity_new"]}
        with self.db.session() as s:
            toks = s.scalars(select(Token).where(Token.active.is_(True), Token.last_seen >= now - FRESH_FOR_TIER2)).all()
            held = set(self._held_token_ids(s))
            ranked = []
            for t in toks:
                snap = self.latest_snapshot(t.id, s)
                if snap is None or snap.liquidity_usd is None:
                    continue
                if t.id not in held:
                    if t.classification == "C" or snap.liquidity_usd < min_liq.get(t.category or "intermediate", 50_000):
                        continue
                    if not snap.volume.get("h1"):
                        continue
                ranked.append((t.id in held, snap.volume.get("h1", 0), t))
            ranked.sort(key=lambda r: (r[0], r[1]), reverse=True)
            chosen = [t for _, _, t in ranked[:limit]]
            chosen_ids = {t.id for t in chosen}
            for t in toks:
                t.tier = 2 if t.id in chosen_ids else 1
        self.tier_counts["nivel2"] = len(chosen)
        return chosen

    async def refresh_candles(self, tokens: list[Token] | None = None) -> int:
        tokens = tokens if tokens is not None else self.tier2_tokens()
        now = utcnow()
        due = sorted((t for t in tokens if now - self._candles_at.get(t.id, datetime.min.replace(tzinfo=timezone.utc)) >= CANDLE_REFRESH),
                     key=lambda t: self._candles_at.get(t.id, datetime.min.replace(tzinfo=timezone.utc)))
        done = 0
        for t in due:
            if not t.pair_address:
                continue
            try:
                candles = await self.gecko.ohlcv(Chain(t.chain), t.pair_address, aggregate=5, limit=100)
            except ProviderError as exc:
                self.log_event("warn", "coleta", f"Candles {t.symbol}: {exc.message}")
                if exc.status == 429 or exc.status is None:
                    break  # respeita o limite do provedor
                continue
            self.db.upsert_candles(t.id, "5m", candles, "geckoterminal")
            self._candles_at[t.id] = utcnow()
            done += 1
        return done

    async def ensure_security(self, token: Token, now: datetime | None = None) -> list[SecurityReport]:
        now = now or utcnow()
        reports = self.latest_security(token.id)
        fresh = {r.source for r in reports if now - r.observed_at <= SECURITY_MAX_AGE}
        chain = Chain(token.chain)
        for name, fetch in (("goplus", self.goplus.token_security), ("geckoterminal", self.gecko.token_info)):
            if name in fresh:
                continue
            try:
                rep = await fetch(chain, token.address)
            except ProviderError as exc:
                self.log_event("warn", "seguranca", f"{name} {token.symbol}: {exc.message}")
                continue
            if rep is None:
                continue
            with self.db.session() as s:
                s.add(SecurityReportRow(token_id=token.id, source=name, observed_at=rep.observed_at, data=rep.model_dump(mode="json")))
        return self.latest_security(token.id)

    # ---------- leitura ----------
    def latest_snapshot(self, token_id: int, s=None) -> PairSnapshot | None:
        def q(sess):
            row = sess.scalars(select(Snapshot).where(Snapshot.token_id == token_id).order_by(Snapshot.observed_at.desc()).limit(1)).first()
            return PairSnapshot.model_validate(row.data) if row else None

        if s is not None:
            return q(s)
        with self.db.session() as sess:
            return q(sess)

    def history(self, token_id: int, since: datetime, until: datetime | None = None) -> list[PairSnapshot]:
        with self.db.session() as s:
            stmt = select(Snapshot).where(Snapshot.token_id == token_id, Snapshot.observed_at >= since)
            if until is not None:
                stmt = stmt.where(Snapshot.observed_at <= until)
            rows = s.scalars(stmt.order_by(Snapshot.observed_at)).all()
            return [PairSnapshot.model_validate(r.data) for r in rows]

    def candles_df(self, token_id: int, limit: int = 120) -> pd.DataFrame:
        with self.db.session() as s:
            rows = s.scalars(
                select(CandleRow).where(CandleRow.token_id == token_id, CandleRow.tf == "5m").order_by(CandleRow.ts.desc()).limit(limit)
            ).all()
            candles = [Candle(ts=r.ts, open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume) for r in rows]
        return candles_to_frame(sorted(candles, key=lambda c: c.ts))

    def latest_security(self, token_id: int) -> list[SecurityReport]:
        with self.db.session() as s:
            rows = s.scalars(
                select(SecurityReportRow).where(SecurityReportRow.token_id == token_id).order_by(SecurityReportRow.observed_at.desc()).limit(10)
            ).all()
            latest: dict[str, SecurityReport] = {}
            for r in rows:
                latest.setdefault(r.source, SecurityReport.model_validate(r.data))
        return list(latest.values())

    def market_regime(self, now: datetime | None = None) -> float:
        """Fração da liquidez monitorada com variação positiva em 1 h (0–1)."""
        now = now or utcnow()
        up = total = 0.0
        with self.db.session() as s:
            ids = s.scalars(select(Token.id).where(Token.last_seen >= now - FRESH_FOR_TIER2)).all()
            for tid in ids:
                snap = self.latest_snapshot(tid, s)
                if snap is None or not snap.liquidity_usd or "h1" not in snap.price_change:
                    continue
                total += snap.liquidity_usd
                if snap.price_change["h1"] > 0:
                    up += snap.liquidity_usd
        return up / total if total else 0.5
