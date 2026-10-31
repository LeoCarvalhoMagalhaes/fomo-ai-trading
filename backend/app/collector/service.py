"""Coleta e armazenamento de dados de mercado em dois níveis (spec 2).

Nível 1: tokens descobertos (pools novos e em alta) atualizados pela DexScreener em lote.
Nível 2: até N ativos pré-selecionados recebem candles de 5 min e checagem de segurança.
Todo dado gravado carrega horário, origem e confiabilidade.
"""
import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import select, update

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
CANDLE_REFRESH = timedelta(minutes=5)
SECURITY_MAX_AGE = timedelta(minutes=30)
FRESH_FOR_TIER2 = timedelta(minutes=5)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Preços recentes guardados na memória: o banco online cobra tráfego de saída, e o ciclo rápido lê os mesmos
# snapshots a cada minuto. Cobre a janela de histórico das estratégias (30 min) e a apuração de resultados (60 min).
RECENT_WINDOW = timedelta(minutes=90)
# Tokens vistos nas últimas 24 h ficam na memória (a coleta usa no máximo 6 h); os outros são lidos sob demanda
TOKEN_MEMORY = timedelta(hours=24)
CANDLE_MEMORY = 300  # candles de 5 min por token (25 h); a análise usa 120 e a página do ativo, 200
TOKEN_FIELDS = ("symbol", "name", "pair_address", "dex_id", "pair_created_at", "category", "last_seen", "active")


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
        self._recent: dict[int, deque[PairSnapshot]] = {}
        self._memory_since = utcnow()  # a memória tem todos os snapshots gravados a partir daqui
        self._tokens: dict[int, Token] = {}
        self._token_ids: dict[tuple[str, str], int] = {}
        self._candles: dict[int, list[Candle]] = {}
        self._security: dict[int, dict[str, SecurityReport]] = {}
        self._load_tokens()
        self._load_recent()

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
    # ---------- tokens na memória ----------
    def _load_tokens(self) -> None:
        with self.db.session() as s:
            for tok in s.scalars(select(Token).where(Token.last_seen >= self._memory_since - TOKEN_MEMORY)):
                self._keep_token(tok)

    def _keep_token(self, tok: Token) -> None:
        self._tokens[tok.id] = tok
        self._token_ids[(tok.chain, tok.address)] = tok.id

    def token(self, token_id: int) -> Token | None:
        """Token da memória (objeto desligado do banco: só leitura; alterações passam por este serviço)."""
        tok = self._tokens.get(token_id)
        if tok is None:
            with self.db.session() as s:
                tok = s.get(Token, token_id)
            if tok is not None:
                self._keep_token(tok)
        return tok

    def set_classification(self, token_id: int, cls: str, reasons: list[str]) -> str | None:
        tok = self.token(token_id)
        previous = tok.classification
        with self.db.session() as s:
            s.execute(update(Token).where(Token.id == token_id).values(classification=cls, class_reasons=reasons))
        tok.classification = cls
        tok.class_reasons = reasons
        return previous

    def forget_stale_tokens(self, now: datetime | None = None) -> None:
        cutoff = (now or utcnow()) - TOKEN_MEMORY
        for tid in [tid for tid, t in self._tokens.items() if t.last_seen < cutoff]:
            tok = self._tokens.pop(tid)
            self._token_ids.pop((tok.chain, tok.address), None)
            self._candles.pop(tid, None)
            self._security.pop(tid, None)
            self._recent.pop(tid, None)

    @staticmethod
    def _apply_snapshot(tok: Token, snap: PairSnapshot, now: datetime) -> None:
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

    def _store_snapshot(self, s, token_id: int, snap: PairSnapshot) -> None:
        s.add(Snapshot(token_id=token_id, observed_at=snap.observed_at, source=snap.source, price_usd=snap.price_usd,
                       liquidity_usd=snap.liquidity_usd, reliability=snap.reliability, data=snap.model_dump(mode="json")))

    def _store_many(self, snaps: list[PairSnapshot], via: str) -> None:
        """Grava snapshots e atualiza os tokens sem relê-los: os conhecidos são atualizados em lote pela chave."""
        now = utcnow()
        stored, new_tokens, changed = [], {}, {}
        with self.db.session() as s:
            for snap in snaps:
                key = (snap.chain.value, snap.token_address)
                tid = self._token_ids.get(key)
                if tid is not None and tid in self._tokens:
                    tok = self._tokens[tid]
                    self._apply_snapshot(tok, snap, now)
                    changed[tid] = {"id": tid, **{f: getattr(tok, f) for f in TOKEN_FIELDS}}
                else:
                    tok = new_tokens.get(key) or s.scalars(
                        select(Token).where(Token.chain == key[0], Token.address == key[1])).first()
                    if tok is None:
                        tok = Token(chain=key[0], address=key[1], symbol=snap.symbol[:64], name=snap.name[:128],
                                    discovered_via=via, first_seen=now)
                        s.add(tok)
                    self._apply_snapshot(tok, snap, now)
                    s.flush()
                    new_tokens[key] = tok
                self._store_snapshot(s, tok.id, snap)
                stored.append((tok.id, snap))
            if changed:
                s.execute(update(Token), list(changed.values()))
        for tok in new_tokens.values():  # só depois de gravado no banco
            self._keep_token(tok)
        for token_id, snap in stored:
            self._remember(token_id, snap)

    def _load_recent(self) -> None:
        """Ao iniciar, uma consulta traz a última janela; depois disso os preços recentes saem da memória."""
        since = self._memory_since - RECENT_WINDOW
        with self.db.session() as s:
            rows = s.execute(select(Snapshot.token_id, Snapshot.data).where(Snapshot.observed_at >= since)
                             .order_by(Snapshot.observed_at)).all()
        for token_id, data in rows:
            self._remember(token_id, PairSnapshot.model_validate(data))
        self._memory_since = since

    def _remember(self, token_id: int, snap: PairSnapshot) -> None:
        dq = self._recent.setdefault(token_id, deque())
        dq.append(snap)
        if len(dq) > 1 and dq[-2].observed_at > snap.observed_at:
            self._recent[token_id] = dq = deque(sorted(dq, key=lambda x: x.observed_at))
        while dq[0].observed_at < dq[-1].observed_at - RECENT_WINDOW:
            dq.popleft()

    def _memory_covers(self, token_id: int, since: datetime) -> bool:
        if since < self._memory_since:
            return False
        dq = self._recent.get(token_id)
        return not dq or since >= dq[-1].observed_at - RECENT_WINDOW

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
        recent = sorted((t for t in self._tokens.values()
                         if t.active and t.last_seen >= now - TIER1_WINDOW and t.classification != "C"),
                        key=lambda t: t.last_seen, reverse=True)[:TIER1_MAX]
        with self.db.session() as s:
            held = self._held_token_ids(s)
        by_chain: dict[str, set[str]] = defaultdict(set)
        for t in [*recent, *filter(None, map(self.token, held))]:
            by_chain[t.chain].add(t.address)
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
        toks = [t for t in self._tokens.values() if t.active and t.last_seen >= now - FRESH_FOR_TIER2]
        with self.db.session() as s:
            held = set(self._held_token_ids(s))
        ranked = []
        for t in toks:
            snap = self.latest_snapshot(t.id)
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
        tiers = [{"id": t.id, "tier": 2 if t.id in chosen_ids else 1} for t in toks]
        tiers = [x for x in tiers if self._tokens[x["id"]].tier != x["tier"]]
        if tiers:
            with self.db.session() as s:
                s.execute(update(Token), tiers)
            for x in tiers:
                self._tokens[x["id"]].tier = x["tier"]
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
            if t.id in self._candles:
                merged = {c.ts: c for c in self._candles[t.id]} | {c.ts: c for c in candles}
                self._candles[t.id] = sorted(merged.values(), key=lambda c: c.ts)[-CANDLE_MEMORY:]
            self._candles_at[t.id] = utcnow()
            done += 1
        return done

    async def ensure_security(self, token: Token, now: datetime | None = None) -> list[SecurityReport]:
        now = now or utcnow()
        reports = self.latest_security(token.id)
        fresh = {r.source for r in reports if now - r.observed_at <= SECURITY_MAX_AGE}
        chain = Chain(token.chain)
        sources = [("goplus", self.goplus.token_security)]
        if token.category == "new":
            # segunda fonte só para tokens novos (classe A exige confirmação); o GeckoTerminal tem orçamento curto
            sources.append(("geckoterminal", self.gecko.token_info))
        for name, fetch in sources:
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
            self._security.setdefault(token.id, {})[name] = rep
        return self.latest_security(token.id)

    # ---------- leitura ----------
    def latest_snapshot(self, token_id: int, s=None) -> PairSnapshot | None:
        if self._recent.get(token_id):
            return self._recent[token_id][-1]
        def q(sess):
            row = sess.scalars(select(Snapshot).where(Snapshot.token_id == token_id).order_by(Snapshot.observed_at.desc()).limit(1)).first()
            return PairSnapshot.model_validate(row.data) if row else None

        if s is not None:
            return q(s)
        with self.db.session() as sess:
            return q(sess)

    def history(self, token_id: int, since: datetime, until: datetime | None = None) -> list[PairSnapshot]:
        if self._memory_covers(token_id, since):
            return [x for x in self._recent.get(token_id, ())
                    if x.observed_at >= since and (until is None or x.observed_at <= until)]
        with self.db.session() as s:
            stmt = select(Snapshot).where(Snapshot.token_id == token_id, Snapshot.observed_at >= since)
            if until is not None:
                stmt = stmt.where(Snapshot.observed_at <= until)
            rows = s.scalars(stmt.order_by(Snapshot.observed_at)).all()
            return [PairSnapshot.model_validate(r.data) for r in rows]

    def candles_df(self, token_id: int, limit: int = 120) -> pd.DataFrame:
        candles = self._candles.get(token_id)
        if candles is None or limit > CANDLE_MEMORY:
            with self.db.session() as s:
                rows = s.scalars(
                    select(CandleRow).where(CandleRow.token_id == token_id, CandleRow.tf == "5m")
                    .order_by(CandleRow.ts.desc()).limit(max(limit, CANDLE_MEMORY))
                ).all()
                candles = sorted((Candle(ts=r.ts, open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume)
                                  for r in rows), key=lambda c: c.ts)
            if limit <= CANDLE_MEMORY:
                self._candles[token_id] = candles
        return candles_to_frame(candles[-limit:])

    def latest_security(self, token_id: int) -> list[SecurityReport]:
        if token_id in self._security:
            return list(self._security[token_id].values())
        with self.db.session() as s:
            rows = s.scalars(
                select(SecurityReportRow).where(SecurityReportRow.token_id == token_id).order_by(SecurityReportRow.observed_at.desc()).limit(10)
            ).all()
            latest: dict[str, SecurityReport] = {}
            for r in rows:
                latest.setdefault(r.source, SecurityReport.model_validate(r.data))
        self._security[token_id] = latest
        return list(latest.values())

    def market_regime(self, now: datetime | None = None) -> float:
        """Fração da liquidez monitorada com variação positiva em 1 h (0–1)."""
        now = now or utcnow()
        up = total = 0.0
        for tid in [t.id for t in self._tokens.values() if t.last_seen >= now - FRESH_FOR_TIER2]:
            snap = self.latest_snapshot(tid)
            if snap is None or not snap.liquidity_usd or "h1" not in snap.price_change:
                continue
            total += snap.liquidity_usd
            if snap.price_change["h1"] > 0:
                up += snap.liquidity_usd
        return up / total if total else 0.5
