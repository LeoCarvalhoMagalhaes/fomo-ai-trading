"""Ciclo de análise (spec 4.2): avalia o nível 2, compara oportunidades, aplica o Risk Manager e registra tudo."""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.chains import CHAINS, Chain
from app.collector.service import MarketService
from app.config import SCORE_COMPONENTS
from app.costs import estimate_costs
from app.db.models import Cycle, Evaluation, Recommendation, Token, Trade
from app.db.runtime_settings import RuntimeSettings
from app.db.session import Database
from app.market.manipulation import detect_manipulation
from app.market.reliability import is_stale, reliability
from app.newtokens.classify import classify_new_token
from app.notify.hub import Notifier
from app.portfolio.ledger import book_state, close_trade, open_trade
from app.recommend.format import NO_TRADE_MESSAGE, build_recommendation, render_text, usd_price
from app.recommend.lifecycle import should_expire
from app.risk.manager import OpenPosition, RiskLimits, TradeProposal, evaluate
from app.scoring.engine import score_signal
from app.security.rules import evaluate_security
from app.strategy.base import AnalysisContext
from app.strategy.indicators import add_indicators
from app.strategy.registry import ALL_STRATEGIES

log = logging.getLogger(__name__)
HISTORY_WINDOW = timedelta(minutes=30)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CycleResult:
    cycle_id: int
    kind: str
    analyzed: int
    candidates: int
    recommendations: int
    rejections: int
    message: str


@dataclass
class Candidate:
    token: Token
    ctx: AnalysisContext
    signal: object
    score: object
    decision: object
    security: object
    manip: object
    evaluation_id: int


class AnalysisEngine:
    def __init__(self, db: Database, market: MarketService, notifier: Notifier, runtime: RuntimeSettings, broadcast,
                 strategies=None):
        self.db = db
        self.market = market
        self.notifier = notifier
        self.runtime = runtime
        self.broadcast = broadcast
        self.strategies = ALL_STRATEGIES if strategies is None else strategies
        self.lock = asyncio.Lock()
        self.last_cycle: dict | None = None
        self.last_trigger: str | None = None
        self.next_full_at: datetime | None = None
        self.state = "INICIANDO"

    # ---------- estado do livro ----------
    def _book(self, s, cfg: dict, limits: RiskLimits, now: datetime):
        book = book_state(s, cfg["mode"], now, limits, paused=bool(cfg["monitoring.paused"]))
        # Recomendações ativas ainda não executadas reservam capital: nunca supor que o capital está todo livre.
        active = s.execute(
            select(Token.address, Recommendation.category, Recommendation.amount_usd)
            .join(Token, Token.id == Recommendation.token_id)
            .where(Recommendation.status == "ATIVA")
        ).all()
        held = {p.token_address for p in book.open_positions}
        book.open_positions += [OpenPosition(a, c, amt) for a, c, amt in active if a not in held]
        return book

    def _run_strategies(self, ctx: AnalysisContext):
        out = []
        for st in self.strategies:
            if ctx.category in st.categories and len(ctx.df) >= st.min_candles:
                sig = st.evaluate(ctx)
                if sig is not None:
                    out.append(sig)
        return out

    # ---------- ciclo ----------
    async def run_cycle(self, kind: str = "quick", trigger: str = "agenda") -> CycleResult:
        async with self.lock:
            self.last_trigger = trigger
            try:
                result = await self._cycle(kind, trigger)
            except Exception as exc:  # falha crítica: bloqueia recomendações e registra
                log.exception("falha no ciclo")
                self.state = "BLOQUEADO"
                self.market.log_event("error", "ciclo", f"Falha crítica no ciclo: {exc}")
                result = CycleResult(0, kind, 0, 0, 0, 0, f"BLOQUEADO — falha crítica no ciclo: {exc}")
            self.last_cycle = {**result.__dict__, "finished_at": utcnow().isoformat(), "trigger": trigger}
            await self.broadcast({"type": "cycle", "data": self.last_cycle})
            return result

    async def _cycle(self, kind: str, trigger: str) -> CycleResult:
        cfg = self.runtime.all()
        with self.db.session() as s:
            cycle = Cycle(kind=kind, trigger=trigger)
            s.add(cycle)
            s.flush()
            cycle_id = cycle.id

        if cfg["monitoring.paused"]:
            self.state = "PAUSADO"
            return self._finish(cycle_id, kind, 0, 0, 0, 0, "Monitoramento pausado pelo usuário")

        if kind == "full":
            await self.market.discover(trending=True)
            await self.market.refresh_tier1()

        now = utcnow()
        blocked = self.market.data_blocked(now)
        if blocked:
            # o ciclo pode ter esperado outro terminar: atualiza os preços antes de declarar dados obsoletos
            await self.market.refresh_tier1()
            now = utcnow()
            blocked = self.market.data_blocked(now)
        if blocked:
            self.state = "BLOQUEADO"
            await self.notifier.notify("falha_coleta", "falha_coleta", "Coleta de dados com falha",
                                       f"Recomendações bloqueadas: {blocked}.", severity="alta")
            return self._finish(cycle_id, kind, 0, 0, 0, 0, f"BLOQUEADO — {blocked}. Nenhuma recomendação é emitida sem dados.")

        tokens = self.market.tier2_tokens(now)  # candles: a tarefa contínua cuida, dentro do orçamento do provedor

        limits = RiskLimits.from_settings(cfg)
        weights = {k: float(cfg[f"score.weight.{k}"]) for k in SCORE_COMPONENTS}
        min_liq = {"established": cfg["market.min_liquidity_established"], "intermediate": cfg["market.min_liquidity_established"],
                   "new": cfg["market.min_liquidity_new"]}
        regime = self.market.market_regime(now)
        candidates: list[Candidate] = []
        analyzed = rejections = 0

        for token in tokens:
            snap = self.market.latest_snapshot(token.id)
            if snap is None or snap.price_usd is None or is_stale(snap, now, int(cfg["data.max_price_age_s"])):
                continue
            analyzed += 1
            history = self.market.history(token.id, now - HISTORY_WINDOW)
            category = token.category or "intermediate"
            reports = await self.market.ensure_security(token, now) if kind == "full" else self.market.latest_security(token.id)
            verdict = evaluate_security(reports, CHAINS[Chain(token.chain)].family, category)
            manip = detect_manipulation(snap, history[:-1], category, min_liq)
            df = self.market.candles_df(token.id)
            other = next((h.price_usd for h in reversed(history) if h.source != snap.source and h.price_usd), None)
            rel = reliability(snap, other, now, int(cfg["data.max_price_age_s"]))
            classification = None
            if category == "new":
                classification, class_reasons = classify_new_token(snap, history, verdict, manip, now)
                await self._update_classification(token, classification, class_reasons, snap)
            if df.empty:
                if kind == "full":
                    rejections += self._record_rejection(cycle_id, token, None, category, snap.price_usd, ["Sem candles disponíveis"])
                continue
            ctx = AnalysisContext(
                token={"id": token.id, "symbol": token.symbol, "name": token.name, "chain": token.chain,
                       "address": token.address, "pair_address": token.pair_address},
                category=category, df=add_indicators(df), snap=snap, history=history, now=now, classification=classification,
            )
            signals = self._run_strategies(ctx)
            if not signals:
                if kind == "full":
                    reasons = verdict.blocks + manip.blocks or ["Nenhuma estratégia com condições de entrada"]
                    rejections += self._record_rejection(cycle_id, token, None, category, snap.price_usd, reasons)
                continue
            with self.db.session() as s:
                book = self._book(s, cfg, limits, now)
            for sig in signals:
                desired = limits.new_max_usd if category == "new" else limits.established_max_usd
                costs = estimate_costs(Chain(token.chain), desired, snap.liquidity_usd, cfg)
                score = score_signal(ctx, sig, costs, verdict, manip, regime, rel, weights)
                proposal = TradeProposal(
                    chain=Chain(token.chain), token_address=token.address, strategy=sig.strategy, category=category,
                    score=score.total, price=sig.price, stop=sig.stop, target1=sig.target1,
                    liquidity_usd=snap.liquidity_usd, data_reliability=rel, blocks=verdict.blocks + manip.blocks,
                )
                decision = evaluate(proposal, book, limits, now)
                ev_id = self._record_evaluation(cycle_id, token, sig, category, score, decision)
                if decision.status == "VETADA":
                    rejections += 1
                else:
                    candidates.append(Candidate(token, ctx, sig, score, decision, verdict, manip, ev_id))

        created = await self._select_and_publish(candidates, cfg, limits, now)
        msg = NO_TRADE_MESSAGE if not created else f"{len(created)} recomendação(ões) emitida(s)"
        self.state = "OPERANDO"
        return self._finish(cycle_id, kind, analyzed, len(candidates), len(created), rejections, msg)

    async def _select_and_publish(self, candidates: list[Candidate], cfg: dict, limits: RiskLimits, now: datetime) -> list[int]:
        """Compara todas as oportunidades: maior nota primeiro, desempate pelo R:R líquido. Reavalia o risco a cada escolha."""
        candidates.sort(key=lambda c: (c.score.total, c.decision.net_rr or 0), reverse=True)
        created: list[int] = []
        seen_tokens: set[int] = set()
        for c in candidates:
            if c.token.id in seen_tokens:
                continue
            with self.db.session() as s:
                book = self._book(s, cfg, limits, now)
                proposal = TradeProposal(
                    chain=Chain(c.token.chain), token_address=c.token.address, strategy=c.signal.strategy,
                    category=c.ctx.category, score=c.score.total, price=c.signal.price, stop=c.signal.stop,
                    target1=c.signal.target1, liquidity_usd=c.ctx.snap.liquidity_usd,
                    data_reliability=c.decision.costs and 1.0 or 1.0, blocks=[],
                )
                decision = evaluate(proposal, book, limits, now)
                if decision.status == "VETADA":
                    ev = s.get(Evaluation, c.evaluation_id)
                    ev.decision = "REJEITADA"
                    ev.reasons = decision.reasons
                    continue
                c.decision = decision
                payload = build_recommendation(
                    c.ctx, c.signal, c.score, decision, c.security, c.manip,
                    [{"fonte": c.ctx.snap.source, "horario": c.ctx.snap.observed_at},
                     *[{"fonte": r, "horario": now} for r in c.security.sources]],
                    now,
                )
                text = render_text(payload)
                rec = Recommendation(
                    token_id=c.token.id, evaluation_id=c.evaluation_id, strategy=c.signal.strategy, category=c.ctx.category,
                    analysis_at=c.ctx.snap.observed_at, created_at=now,
                    expires_at=now + timedelta(minutes=float(cfg["rec.ttl_minutes"])),
                    price_observed=c.signal.price, amount_usd=decision.amount_usd, entry_low=c.signal.entry_low,
                    entry_high=c.signal.entry_high, stop=c.signal.stop, target1=c.signal.target1, target2=c.signal.target2,
                    score=c.score.total, payload=payload, text=text,
                )
                s.add(rec)
                s.flush()
                rec_id = rec.id
                ev = s.get(Evaluation, c.evaluation_id)
                ev.decision = "RECOMENDADA"
                ev.reasons = decision.reasons
                self._paper_open(s, rec, c, decision, cfg, limits, now)
            created.append(rec_id)
            seen_tokens.add(c.token.id)
            severity = "alta" if c.score.total >= 90 else "media"
            await self.notifier.notify(
                "oportunidade", f"rec:{c.token.id}:{c.signal.strategy}",
                f"{'Alta prioridade' if c.score.total >= 90 else 'Oportunidade'}: {c.token.symbol} ({c.score.total:.0f}/100)",
                f"Compra de US$ {decision.amount_usd:.2f} a {usd_price(c.signal.price)}, alvo 1 {usd_price(c.signal.target1)}, "
                f"stop {usd_price(c.signal.stop)}. Confirme no app da FOMO.",
                severity=severity, data={"recommendation_id": rec_id},
            )
            await self.broadcast({"type": "recommendation", "data": {"id": rec_id}})
        return created

    def _paper_open(self, s, rec: Recommendation, c: Candidate, decision, cfg: dict, limits: RiskLimits, now: datetime) -> None:
        """Livro SIM: toda recomendação aprovada é executada no papel com custos estimados."""
        costs = decision.costs
        entry = c.signal.price * (1 + (costs.slippage_pct + costs.impact_pct) / 100)
        fee = decision.amount_usd * (costs.fomo_fee_pct + costs.pool_fee_pct) / 100 + costs.gas_usd
        open_trade(s, "SIM", c.token.id, decision.amount_usd, entry, fee, now, limits=limits, now=now,
                   recommendation_id=rec.id, strategy=c.signal.strategy, category=c.ctx.category,
                   stop=c.signal.stop, target1=c.signal.target1, target2=c.signal.target2, note="Execução simulada automática")

    async def _update_classification(self, token: Token, cls: str, reasons: list[str], snap) -> None:
        with self.db.session() as s:
            row = s.get(Token, token.id)
            previous = row.classification
            row.classification = cls
            row.class_reasons = reasons
        if cls == "A" and previous != "A":
            await self.notifier.notify("novo_token", f"novo:{token.id}", f"Novo token classe A: {token.symbol}",
                                       f"{CHAINS[Chain(token.chain)].label}, liquidez US$ {snap.liquidity_usd or 0:,.0f}. "
                                       "Classe A não é recomendação: aguarde o ciclo de análise.", severity="media")
        if cls == "C" and previous in ("A", "B"):
            await self.notifier.notify("risco_critico", f"risco:{token.id}", f"Risco crítico: {token.symbol}",
                                       "; ".join(reasons), severity="alta", relevant_change=True)

    # ---------- registro ----------
    def _record_rejection(self, cycle_id, token, strategy, category, price, reasons) -> int:
        with self.db.session() as s:
            s.add(Evaluation(cycle_id=cycle_id, token_id=token.id, strategy=strategy, category=category,
                             decision="REJEITADA", reasons=reasons, price=price))
        return 1

    def _record_evaluation(self, cycle_id, token, sig, category, score, decision) -> int:
        with self.db.session() as s:
            ev = Evaluation(cycle_id=cycle_id, token_id=token.id, strategy=sig.strategy, category=category,
                            score=score.total, band=score.band, components=score.components_dict(),
                            decision="REJEITADA" if decision.status == "VETADA" else "CANDIDATA",
                            reasons=decision.reasons, price=sig.price, stop=sig.stop, target1=sig.target1)
            s.add(ev)
            s.flush()
            return ev.id

    def _finish(self, cycle_id, kind, analyzed, candidates, recs, rejections, message) -> CycleResult:
        with self.db.session() as s:
            row = s.get(Cycle, cycle_id)
            if row is not None:
                row.finished_at = utcnow()
                row.analyzed, row.candidates, row.recommendations, row.message = analyzed, candidates, recs, message
            # avaliações que não viraram recomendação nem foram vetadas ficam como rejeitadas pela comparação
            for ev in s.scalars(select(Evaluation).where(Evaluation.cycle_id == cycle_id, Evaluation.decision == "CANDIDATA")):
                ev.decision = "REJEITADA"
                ev.reasons = list(ev.reasons or []) + ["Superada por oportunidade melhor no mesmo ativo ou ciclo"]
        return CycleResult(cycle_id, kind, analyzed, candidates, recs, rejections, message)

    # ---------- acompanhamento ----------
    async def expire_recommendations(self) -> int:
        now = utcnow()
        cfg = self.runtime.all()
        expired = 0
        with self.db.session() as s:
            recs = s.scalars(select(Recommendation).where(Recommendation.status == "ATIVA")).all()
            items = [(r.id, r.token_id, r) for r in recs]
        for rec_id, token_id, rec in items:
            snap = self.market.latest_snapshot(token_id)
            blocks = []
            if snap is not None:
                with self.db.session() as s:
                    tok = s.get(Token, token_id)
                    category = tok.category or "intermediate"
                    if tok.classification == "C":
                        blocks.append("Token reclassificado como C (evitar)")
                history = self.market.history(token_id, now - timedelta(minutes=15))
                blocks += detect_manipulation(snap, history[:-1], category).blocks
            reason = should_expire(rec, snap, now, blocks, int(cfg["data.max_price_age_s"]), float(cfg["rec.max_entry_run_pct"]))
            if reason:
                with self.db.session() as s:
                    r = s.get(Recommendation, rec_id)
                    r.status, r.status_reason, r.status_changed_at = "EXPIRADA", reason, now
                    symbol = s.get(Token, token_id).symbol
                expired += 1
                await self.notifier.notify("expirada", f"exp:{rec_id}", f"Recomendação expirada: {symbol}", reason)
                await self.broadcast({"type": "recommendation", "data": {"id": rec_id}})
        return expired

    async def monitor_positions(self) -> None:
        now = utcnow()
        cfg = self.runtime.all()
        horizon = timedelta(minutes=float(cfg["rec.horizon_minutes"]))
        with self.db.session() as s:
            trades = s.execute(select(Trade, Token).join(Token, Token.id == Trade.token_id).where(Trade.status == "OPEN")).all()
            items = [(t.id, t.ledger, t.token_id, t.stop, t.target1, t.target2, t.executed_at, list(t.alerts_sent or []),
                      tok.symbol, tok.chain, t.amount_usd) for t, tok in trades]
        for trade_id, ledger, token_id, stop, t1, t2, executed_at, alerts, symbol, chain, amount in items:
            snap = self.market.latest_snapshot(token_id)
            if snap is None or snap.price_usd is None:
                continue
            price = snap.price_usd
            with self.db.session() as s:
                tr = s.get(Trade, trade_id)
                tr.last_price, tr.last_price_at = price, snap.observed_at
            event = None
            if stop and price <= stop:
                event = "stop"
            elif t1 and price >= t1:
                event = "alvo1"
            elif now - executed_at >= horizon:
                event = "tempo"
            if event is None:
                continue
            labels = {"stop": "stop de referência atingido", "alvo1": "alvo 1 atingido", "tempo": "horizonte de 60 min encerrado"}
            if ledger == "SIM":
                costs = estimate_costs(Chain(chain), amount, snap.liquidity_usd, cfg)
                exit_price = price * (1 - (costs.slippage_pct + min(costs.impact_pct, 50)) / 100)
                fee = amount * (costs.fomo_fee_pct + costs.pool_fee_pct) / 100 + costs.gas_usd
                with self.db.session() as s:
                    tr = close_trade(s, trade_id, exit_price, fee, now, event)
                    pnl = tr.pnl_usd
                await self.notifier.notify("encerrada", f"close:{trade_id}", f"Simulação encerrada: {symbol}",
                                           f"{labels[event].capitalize()}; resultado simulado US$ {pnl:+.2f}.")
                await self._check_daily_loss("SIM")
            elif event not in alerts:
                with self.db.session() as s:
                    tr = s.get(Trade, trade_id)
                    tr.alerts_sent = alerts + [event]
                await self.notifier.notify("saida", f"saida:{trade_id}:{event}", f"Condição de saída: {symbol}",
                                           f"{labels[event].capitalize()} (preço observado {usd_price(price)}). "
                                           "Registre o encerramento quando vender na FOMO.", severity="alta")
            await self.broadcast({"type": "portfolio", "data": {"ledger": ledger}})

    async def _check_daily_loss(self, ledger: str) -> None:
        cfg = self.runtime.all()
        limits = RiskLimits.from_settings(cfg)
        now = utcnow()
        with self.db.session() as s:
            book = book_state(s, ledger, now, limits)
        if book.day_realized_pnl <= -limits.max_daily_loss_usd:
            await self.notifier.notify("limite_perda", f"perda:{ledger}:{now.date()}", f"Limite de perda diária atingido ({ledger})",
                                       f"Perda do dia: US$ {book.day_realized_pnl:.2f}. Novas recomendações operacionais suspensas até amanhã (UTC).",
                                       severity="critica")

    async def report_execution(self, rec_id: int, price: float, amount_usd: float, fee_usd: float, executed_at: datetime) -> int:
        """O usuário informa que executou na FOMO. Registra no livro REAL e dispara nova seleção imediata."""
        cfg = self.runtime.all()
        limits = RiskLimits.from_settings(cfg)
        now = utcnow()
        with self.db.session() as s:
            rec = s.get(Recommendation, rec_id)
            if rec is None:
                raise ValueError("recomendação inexistente")
            trade = open_trade(s, "REAL", rec.token_id, amount_usd, price, fee_usd, executed_at, limits=limits, now=now,
                               recommendation_id=rec.id, strategy=rec.strategy, category=rec.category, stop=rec.stop,
                               target1=rec.target1, target2=rec.target2)
            if rec.status != "ATIVA":
                trade.limit_flags = list(trade.limit_flags) + [f"Executada com a recomendação já {rec.status.lower()}"]
            rec.status, rec.status_changed_at, rec.status_reason = "EXECUTADA", now, "Execução informada pelo usuário"
            symbol = s.get(Token, rec.token_id).symbol
            trade_id = trade.id
            flags = list(trade.limit_flags)
        await self.notifier.notify("execucao", f"exec:{trade_id}", f"Operação registrada: {symbol}",
                                   f"US$ {amount_usd:.2f} a {usd_price(price)}." + (f" Alertas: {'; '.join(flags)}" if flags else ""),
                                   severity="alta" if flags else "info")
        self.last_trigger = "execucao"
        asyncio.get_running_loop().create_task(self.run_cycle("full", "execucao"))
        return trade_id

    async def track_outcomes(self) -> int:
        """Registra o que aconteceu 60 min depois de cada avaliação (recomendada ou rejeitada)."""
        now = utcnow()
        horizon = timedelta(minutes=float(self.runtime.get("rec.horizon_minutes")))
        with self.db.session() as s:
            evs = s.scalars(
                select(Evaluation).where(Evaluation.outcome_at.is_(None), Evaluation.price.is_not(None),
                                         Evaluation.created_at <= now - horizon).limit(500)
            ).all()
            items = [(e.id, e.token_id, e.created_at, e.price, e.stop, e.target1) for e in evs]
        done = 0
        for ev_id, token_id, created, price, stop, t1 in items:
            path = self.market.history(token_id, created, created + horizon)
            prices = [p.price_usd for p in path if p.price_usd]
            hit = None
            for p in prices:
                if stop and p <= stop:
                    hit = "stop"
                    break
                if t1 and p >= t1:
                    hit = "alvo1"
                    break
            with self.db.session() as s:
                ev = s.get(Evaluation, ev_id)
                ev.outcome_at = now
                if prices:
                    ev.outcome_price = prices[-1]
                    ev.outcome_return_pct = (prices[-1] / price - 1) * 100
                    ev.outcome_hit = hit or "tempo"
                else:
                    ev.outcome_hit = "sem_dados"
            done += 1
        return done
