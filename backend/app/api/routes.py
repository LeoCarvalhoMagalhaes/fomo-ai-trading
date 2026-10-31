"""Rotas REST. Todas as respostas trazem horários em UTC (ISO 8601)."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select

from app.api.validation import SettingsError, validate_changes
from app.backtest.report import backtest_from_db, filter_report, save_report
from app.chains import CHAINS, Chain
from app.config import DEFAULT_RUNTIME
from app.costs import estimate_costs
from app.db.models import AuditLog, Cycle, Evaluation, Event, Notification, Recommendation, Snapshot, Token, Trade
from app.portfolio.ledger import book_state, close_trade, open_trade
from app.portfolio.metrics import compute_metrics
from app.recommend.format import NO_TRADE_MESSAGE
from app.risk.manager import RiskLimits
from app.security.rules import evaluate_security
from app.strategy.indicators import add_indicators
from app.strategy.registry import ALL_STRATEGIES

router = APIRouter(prefix="/api")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _num(v):
    """JSON não aceita infinito/NaN."""
    if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        return None
    return v


def _clean(obj):
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return _iso(_num(obj))


def token_dict(t: Token) -> dict:
    return {"id": t.id, "chain": t.chain, "chain_label": CHAINS[Chain(t.chain)].label, "address": t.address,
            "symbol": t.symbol, "name": t.name, "pair_address": t.pair_address, "dex_id": t.dex_id,
            "pair_created_at": _iso(t.pair_created_at), "category": t.category, "tier": t.tier,
            "classification": t.classification, "class_reasons": t.class_reasons, "first_seen": _iso(t.first_seen),
            "last_seen": _iso(t.last_seen)}


def rec_dict(r: Recommendation, t: Token | None = None) -> dict:
    d = {"id": r.id, "token_id": r.token_id, "strategy": r.strategy, "category": r.category, "status": r.status,
         "analysis_at": _iso(r.analysis_at), "created_at": _iso(r.created_at), "expires_at": _iso(r.expires_at),
         "status_changed_at": _iso(r.status_changed_at), "status_reason": r.status_reason,
         "price_observed": r.price_observed, "amount_usd": r.amount_usd, "entry_low": r.entry_low,
         "entry_high": r.entry_high, "stop": r.stop, "target1": r.target1, "target2": r.target2, "score": r.score,
         "payload": r.payload, "text": r.text}
    if t is not None:
        d["token"] = token_dict(t)
    return d


def trade_dict(tr: Trade, t: Token | None = None) -> dict:
    d = {c: _iso(getattr(tr, c)) for c in ("id", "ledger", "token_id", "recommendation_id", "strategy", "category", "status",
                                            "amount_usd", "entry_price", "entry_fee_usd", "executed_at", "stop", "target1",
                                            "target2", "exit_price", "exit_fee_usd", "closed_at", "close_reason", "pnl_usd",
                                            "last_price", "last_price_at", "limit_flags", "note")}
    if t is not None:
        d["token"] = token_dict(t)
    return d


def eval_dict(e: Evaluation, t: Token | None = None) -> dict:
    d = {c: _iso(getattr(e, c)) for c in ("id", "cycle_id", "created_at", "token_id", "strategy", "category", "score", "band",
                                           "components", "decision", "reasons", "price", "stop", "target1", "outcome_at",
                                           "outcome_price", "outcome_return_pct", "outcome_hit")}
    if t is not None:
        d["token"] = token_dict(t)
    return d


# ---------- portfólio ----------
def portfolio_summary(request: Request, ledger: str) -> dict:
    st = request.app.state
    cfg = st.runtime.all()
    limits = RiskLimits.from_settings(cfg)
    now = utcnow()
    with st.db.session() as s:
        book = book_state(s, ledger, now, limits)
        rows = s.execute(select(Trade, Token).join(Token, Token.id == Trade.token_id).where(Trade.ledger == ledger)
                         .order_by(Trade.executed_at)).all()
        positions, closed, fees = [], [], 0.0
        for tr, tok in rows:
            fees += (tr.entry_fee_usd or 0) + (tr.exit_fee_usd or 0)
            if tr.status == "OPEN":
                last = tr.last_price
                if last is None:
                    snap = st.market.latest_snapshot(tok.id, s)
                    last = snap.price_usd if snap else None
                d = trade_dict(tr, tok)
                if last:
                    exit_cost = estimate_costs(Chain(tok.chain), tr.amount_usd, 1e12, cfg)
                    exit_fee = tr.amount_usd * (exit_cost.fomo_fee_pct + exit_cost.pool_fee_pct) / 100 + exit_cost.gas_usd
                    d["unrealized_pnl_usd"] = tr.amount_usd * (last / tr.entry_price - 1) - tr.entry_fee_usd - exit_fee
                    d["current_price"] = last
                else:
                    d["unrealized_pnl_usd"] = None
                positions.append(d)
            else:
                closed.append(tr)
    closed.sort(key=lambda t: t.closed_at)
    metrics = compute_metrics([{"pnl_usd": t.pnl_usd or 0, "amount_usd": t.amount_usd, "strategy": t.strategy,
                                "category": t.category} for t in closed])
    exposure_by_token: dict[str, float] = {}
    for p in positions:
        exposure_by_token[p["token"]["symbol"]] = exposure_by_token.get(p["token"]["symbol"], 0) + p["amount_usd"]
    unreal = [p["unrealized_pnl_usd"] for p in positions if p["unrealized_pnl_usd"] is not None]
    return _clean({
        "ledger": ledger,
        "capital_initial": limits.capital_usd,
        "realized_pnl": book.realized_pnl,
        "capital_current": book.capital_current,
        "exposure": book.exposure,
        "new_exposure": book.new_exposure,
        "available": book.capital_current - book.exposure,
        "free_for_trading": max(0.0, book.capital_current - book.exposure - limits.min_reserve_usd),
        "reserve": limits.min_reserve_usd,
        "unrealized_pnl": sum(unreal) if unreal else 0.0,
        "fees_total": fees,
        "return_pct": book.realized_pnl / limits.capital_usd * 100 if limits.capital_usd else None,
        "day_realized_pnl": book.day_realized_pnl,
        "consecutive_losses": book.consecutive_losses,
        "exposure_by_token": exposure_by_token,
        "positions": positions,
        "metrics": metrics,
    })


def sim_observation(request: Request) -> dict:
    with request.app.state.db.session() as s:
        n = s.scalar(select(func.count()).select_from(Trade).where(Trade.ledger == "SIM", Trade.status == "CLOSED"))
        first = s.scalar(select(func.min(Trade.executed_at)).where(Trade.ledger == "SIM"))
    days = (utcnow() - first).days if first else 0
    done = n >= 50 and days >= 14
    return {"closed_sim_trades": n, "days": days, "required_trades": 50, "required_days": 14, "complete": done,
            "message": None if done else
            f"Período de observação em andamento: {n}/50 simulações encerradas e {days}/14 dias. "
            "Use o modo REAL só depois de avaliar os resultados simulados."}


@router.get("/dashboard")
def dashboard(request: Request):
    st = request.app.state
    cfg = st.runtime.all()
    now = utcnow()
    books = {lg: portfolio_summary(request, lg) for lg in ("SIM", "REAL")}
    with st.db.session() as s:
        best = s.execute(select(Recommendation, Token).join(Token, Token.id == Recommendation.token_id)
                         .where(Recommendation.status == "ATIVA").order_by(desc(Recommendation.score)).limit(1)).first()
        top = s.execute(
            select(Evaluation, Token).join(Token, Token.id == Evaluation.token_id)
            .where(Evaluation.score.is_not(None), Evaluation.created_at >= now - timedelta(hours=2))
            .order_by(desc(Evaluation.score)).limit(40)
        ).all()
        seen, top_scores = set(), []
        for e, t in top:
            if t.id not in seen:
                seen.add(t.id)
                top_scores.append(eval_dict(e, t))
        new = s.scalars(select(Token).where(Token.category == "new", Token.classification.in_(["A", "B"]),
                                            Token.last_seen >= now - timedelta(hours=1))
                        .order_by(Token.classification, desc(Token.last_seen)).limit(8)).all()
        new_tokens = []
        for t in new:
            snap = st.market.latest_snapshot(t.id, s)
            new_tokens.append({**token_dict(t), "price_usd": snap.price_usd if snap else None,
                               "liquidity_usd": snap.liquidity_usd if snap else None})
        alerts = s.scalars(select(Notification).where(Notification.severity.in_(["alta", "critica"]),
                                                      Notification.created_at >= now - timedelta(hours=24))
                           .order_by(desc(Notification.created_at)).limit(10)).all()
        last_cycle = s.scalars(select(Cycle).where(Cycle.finished_at.is_not(None)).order_by(desc(Cycle.id)).limit(1)).first()
    regime = st.market.market_regime(now)
    message = NO_TRADE_MESSAGE if best is None else None
    if st.engine.state == "BLOQUEADO" and last_cycle is not None:
        message = last_cycle.message
    if cfg["monitoring.paused"]:
        message = "Monitoramento pausado pelo usuário."
    return _clean({
        "capital": cfg["risk.capital_usd"],
        "mode": cfg["mode"],
        "paused": cfg["monitoring.paused"],
        "books": books,
        "best_opportunity": rec_dict(*best) if best else None,
        "top_scores": top_scores[:8],
        "new_tokens": new_tokens,
        "market_regime": {"up_fraction": regime, "label": "alta" if regime > 0.55 else "baixa" if regime < 0.45 else "lateral"},
        "last_cycle": {"id": last_cycle.id, "kind": last_cycle.kind, "trigger": last_cycle.trigger,
                       "finished_at": last_cycle.finished_at, "analyzed": last_cycle.analyzed,
                       "recommendations": last_cycle.recommendations, "message": last_cycle.message} if last_cycle else None,
        "next_full_at": st.engine.next_full_at,
        "providers": st.market.provider_status(now),
        "alerts": [{"id": n.id, "title": n.title, "body": n.body, "severity": n.severity, "created_at": n.created_at} for n in alerts],
        "state": st.engine.state,
        "tiers": st.market.tier_counts,
        "message": message,
        "observation": sim_observation(request),
        "round_trip_example": {
            chain.value: estimate_costs(chain, cfg["risk.established_max_usd"], 1_000_000, cfg).round_trip_pct for chain in Chain
        },
    })


@router.get("/opportunities")
def opportunities(request: Request, hours: float = 6, decision: str | None = None, limit: int = 300):
    since = utcnow() - timedelta(hours=hours)
    with request.app.state.db.session() as s:
        q = select(Evaluation, Token).join(Token, Token.id == Evaluation.token_id).where(Evaluation.created_at >= since)
        if decision:
            q = q.where(Evaluation.decision == decision.upper())
        rows = s.execute(q.order_by(desc(Evaluation.created_at)).limit(limit)).all()
        return _clean([eval_dict(e, t) for e, t in rows])


@router.get("/new-tokens")
def new_tokens(request: Request, hours: float = 72):
    st = request.app.state
    since = utcnow() - timedelta(hours=hours)
    with st.db.session() as s:
        toks = s.scalars(select(Token).where(Token.category == "new", Token.last_seen >= since)
                         .order_by(desc(Token.first_seen)).limit(200)).all()
        out = []
        for t in toks:
            snap = st.market.latest_snapshot(t.id, s)
            out.append({**token_dict(t), "snapshot": snap.model_dump(mode="json") if snap else None})
    return _clean(out)


@router.get("/tokens/{token_id}")
def token_detail(request: Request, token_id: int):
    st = request.app.state
    with st.db.session() as s:
        t = s.get(Token, token_id)
        if t is None:
            raise HTTPException(404, "Token não encontrado")
        tok = token_dict(t)
        evals = [eval_dict(e) for e in s.scalars(select(Evaluation).where(Evaluation.token_id == token_id)
                                                 .order_by(desc(Evaluation.created_at)).limit(50))]
        snaps = s.scalars(select(Snapshot).where(Snapshot.token_id == token_id).order_by(desc(Snapshot.observed_at)).limit(120)).all()
        snap_series = [{"t": r.observed_at, "price": r.price_usd, "liquidity": r.liquidity_usd, "source": r.source} for r in reversed(snaps)]
    df = st.market.candles_df(token_id, limit=200)
    candles = []
    if not df.empty:
        ind = add_indicators(df)
        for ts, r in ind.iterrows():
            candles.append({"t": int(ts.timestamp()), "open": r.open, "high": r.high, "low": r.low, "close": r.close,
                            "volume": r.volume, "ema20": _num(r.ema20), "ema50": _num(r.ema50), "bb_up": _num(r.bb_up),
                            "bb_low": _num(r.bb_low), "rsi14": _num(r.rsi14), "vwap": _num(r.vwap)})
    reports = st.market.latest_security(token_id)
    verdict = evaluate_security(reports, CHAINS[Chain(tok["chain"])].family, tok["category"] or "intermediate")
    snap = st.market.latest_snapshot(token_id)
    return _clean({
        "token": tok,
        "snapshot": snap.model_dump(mode="json") if snap else None,
        "snapshots": snap_series,
        "candles": candles,
        "security": {"reports": [r.model_dump(mode="json") for r in reports], "blocks": verdict.blocks,
                     "penalties": [{"motivo": m, "peso": p} for m, p in verdict.penalties],
                     "coverage": verdict.coverage, "sources": verdict.sources,
                     "aviso": "Passar nos filtros não significa que o token é seguro."},
        "evaluations": evals,
    })


@router.get("/tokens")
def tokens(request: Request, q: str = "", limit: int = 50):
    with request.app.state.db.session() as s:
        stmt = select(Token)
        if q:
            stmt = stmt.where((Token.symbol.ilike(f"%{q}%")) | (Token.address == q) | (Token.name.ilike(f"%{q}%")))
        return _clean([token_dict(t) for t in s.scalars(stmt.order_by(desc(Token.last_seen)).limit(limit))])


# ---------- recomendações ----------
@router.get("/recommendations")
def recommendations(request: Request, status: str | None = None, limit: int = 100):
    with request.app.state.db.session() as s:
        q = select(Recommendation, Token).join(Token, Token.id == Recommendation.token_id)
        if status:
            q = q.where(Recommendation.status == status.upper())
        return _clean([rec_dict(r, t) for r, t in s.execute(q.order_by(desc(Recommendation.created_at)).limit(limit))])


@router.get("/recommendations/{rec_id}")
def recommendation(request: Request, rec_id: int):
    with request.app.state.db.session() as s:
        row = s.execute(select(Recommendation, Token).join(Token, Token.id == Recommendation.token_id)
                        .where(Recommendation.id == rec_id)).first()
        if row is None:
            raise HTTPException(404, "Recomendação não encontrada")
        return _clean(rec_dict(*row))


class ExecutedIn(BaseModel):
    price: float = Field(gt=0)
    amount_usd: float = Field(gt=0)
    fee_usd: float = Field(ge=0, default=0)
    executed_at: datetime | None = None


@router.post("/recommendations/{rec_id}/executed")
async def recommendation_executed(request: Request, rec_id: int, body: ExecutedIn):
    executed_at = body.executed_at or utcnow()
    if executed_at.tzinfo is None:
        executed_at = executed_at.replace(tzinfo=timezone.utc)
    try:
        trade_id = await request.app.state.engine.report_execution(rec_id, body.price, body.amount_usd, body.fee_usd, executed_at)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    await request.app.state.ws.broadcast({"type": "portfolio", "data": {"ledger": "REAL"}})
    return {"trade_id": trade_id}


@router.post("/recommendations/{rec_id}/ignored")
async def recommendation_ignored(request: Request, rec_id: int):
    with request.app.state.db.session() as s:
        r = s.get(Recommendation, rec_id)
        if r is None:
            raise HTTPException(404, "Recomendação não encontrada")
        if r.status == "ATIVA":
            r.status, r.status_changed_at, r.status_reason = "IGNORADA", utcnow(), "Ignorada pelo usuário"
    await request.app.state.ws.broadcast({"type": "recommendation", "data": {"id": rec_id}})
    return {"ok": True}


# ---------- operações ----------
@router.get("/portfolio/{ledger}")
def portfolio(request: Request, ledger: str):
    if ledger.upper() not in ("SIM", "REAL"):
        raise HTTPException(400, "Livro inválido")
    return portfolio_summary(request, ledger.upper())


class TradeIn(BaseModel):
    ledger: str
    token_id: int | None = None
    chain: Chain | None = None
    address: str | None = None
    symbol: str | None = None
    category: str = "established"
    amount_usd: float = Field(gt=0)
    price: float = Field(gt=0)
    fee_usd: float = Field(ge=0, default=0)
    executed_at: datetime | None = None
    stop: float | None = None
    target1: float | None = None
    note: str = ""


@router.post("/trades")
async def create_trade(request: Request, body: TradeIn):
    st = request.app.state
    ledger = body.ledger.upper()
    if ledger not in ("SIM", "REAL"):
        raise HTTPException(400, "Livro inválido")
    if body.category not in ("established", "intermediate", "new"):
        raise HTTPException(400, "Categoria inválida")
    now = utcnow()
    limits = RiskLimits.from_settings(st.runtime.all())
    with st.db.session() as s:
        if body.token_id is not None:
            tok = s.get(Token, body.token_id)
        elif body.chain and body.address:
            tok = s.scalars(select(Token).where(Token.chain == body.chain.value, Token.address == body.address)).first()
            if tok is None:
                tok = Token(chain=body.chain.value, address=body.address, symbol=body.symbol or body.address[:6],
                            name=body.symbol or "", category=body.category, discovered_via="manual")
                s.add(tok)
                s.flush()
        else:
            raise HTTPException(400, "Informe token_id ou rede + endereço")
        if tok is None:
            raise HTTPException(404, "Token não encontrado")
        executed_at = body.executed_at or now
        if executed_at.tzinfo is None:
            executed_at = executed_at.replace(tzinfo=timezone.utc)
        tr = open_trade(s, ledger, tok.id, body.amount_usd, body.price, body.fee_usd, executed_at, limits=limits, now=now,
                        category=body.category, stop=body.stop, target1=body.target1, note=body.note or "Registro manual")
        out = trade_dict(tr, tok)
    await st.notifier.notify("execucao", f"manual:{out['id']}", f"Operação registrada ({ledger}): {out['token']['symbol']}",
                             f"US$ {body.amount_usd:.2f} a {body.price}.", severity="alta" if out["limit_flags"] else "info")
    await st.ws.broadcast({"type": "portfolio", "data": {"ledger": ledger}})
    return _clean(out)


class CloseIn(BaseModel):
    price: float = Field(gt=0)
    fee_usd: float = Field(ge=0, default=0)
    closed_at: datetime | None = None
    reason: str = "manual"


@router.post("/trades/{trade_id}/close")
async def close(request: Request, trade_id: int, body: CloseIn):
    st = request.app.state
    closed_at = body.closed_at or utcnow()
    if closed_at.tzinfo is None:
        closed_at = closed_at.replace(tzinfo=timezone.utc)
    with st.db.session() as s:
        try:
            tr = close_trade(s, trade_id, body.price, body.fee_usd, closed_at, body.reason)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        out = trade_dict(tr, s.get(Token, tr.token_id))
    await st.notifier.notify("encerrada", f"close:{trade_id}", f"Operação encerrada: {out['token']['symbol']}",
                             f"Resultado US$ {out['pnl_usd']:+.2f}.")
    await st.engine._check_daily_loss(out["ledger"])
    await st.ws.broadcast({"type": "portfolio", "data": {"ledger": out["ledger"]}})
    return _clean(out)


@router.get("/trades")
def trades(request: Request, ledger: str | None = None, status: str | None = None, limit: int = 500):
    with request.app.state.db.session() as s:
        q = select(Trade, Token).join(Token, Token.id == Trade.token_id)
        if ledger:
            q = q.where(Trade.ledger == ledger.upper())
        if status:
            q = q.where(Trade.status == status.upper())
        return _clean([trade_dict(tr, t) for tr, t in s.execute(q.order_by(desc(Trade.executed_at)).limit(limit))])


# ---------- estatísticas ----------
@router.get("/stats")
def stats(request: Request):
    st = request.app.state
    path = st.settings.data_dir / "backtests" / "ultimo.json"
    backtest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return _clean({
        "SIM": portfolio_summary(request, "SIM")["metrics"],
        "REAL": portfolio_summary(request, "REAL")["metrics"],
        "filtros": filter_report(st.db),
        "backtest": backtest,
        "observacao": sim_observation(request),
        "estrategias": [{"id": s.name, **s.describe()} for s in ALL_STRATEGIES],
    })


@router.post("/backtest/run")
async def run_backtest(request: Request):
    st = request.app.state
    cfg = st.runtime.all()

    def work():
        liquidity = {}
        with st.db.session() as s:
            for tid, liq in s.execute(select(Snapshot.token_id, Snapshot.liquidity_usd).order_by(Snapshot.observed_at)):
                if liq:
                    liquidity[tid] = liq
        report = {"backtest": backtest_from_db(st.db, cfg, liquidity), "filtros": filter_report(st.db)}
        save_report(report, st.settings.data_dir)
        return report

    return _clean(await asyncio.to_thread(work))


# ---------- configurações e controle ----------
@router.get("/settings")
def get_settings(request: Request):
    return {"values": request.app.state.runtime.all(), "defaults": DEFAULT_RUNTIME}


class SettingsIn(BaseModel):
    changes: dict


@router.put("/settings")
async def put_settings(request: Request, body: SettingsIn):
    rs = request.app.state.runtime
    try:
        changes = validate_changes(rs.all(), body.changes)
    except SettingsError as exc:
        raise HTTPException(400, str(exc)) from exc
    for k, v in changes.items():
        rs.set(k, v, actor="usuario")
    await request.app.state.ws.broadcast({"type": "settings", "data": changes})
    return {"values": rs.all()}


@router.get("/providers")
def providers(request: Request):
    st = request.app.state
    m = st.market
    return _clean({
        "providers": m.provider_status(),
        "budgets": {"geckoterminal": st.settings.gecko_rpm, "dexscreener": st.settings.dex_rpm, "goplus": st.settings.goplus_rpm},
        "tiers": m.tier_counts,
        "last_discovery": m.last_discovery,
        "last_tier1": m.last_tier1,
        "demo_key_configured": bool(st.settings.coingecko_demo_key),
        "telegram_configured": bool(st.settings.telegram_bot_token and st.settings.telegram_chat_id),
        "chains": [{"id": c.value, "label": i.label, "gecko": i.gecko_id, "dex": i.dex_id, "goplus": i.goplus_id} for c, i in CHAINS.items()],
    })


@router.get("/logs")
def logs(request: Request, limit: int = 200, level: str | None = None):
    with request.app.state.db.session() as s:
        q = select(Event)
        if level:
            q = q.where(Event.level == level)
        rows = s.scalars(q.order_by(desc(Event.created_at)).limit(limit)).all()
        cycles = s.scalars(select(Cycle).order_by(desc(Cycle.id)).limit(30)).all()
        return _clean({
            "events": [{"id": e.id, "created_at": e.created_at, "level": e.level, "kind": e.kind, "message": e.message, "data": e.data} for e in rows],
            "cycles": [{"id": c.id, "kind": c.kind, "trigger": c.trigger, "started_at": c.started_at, "finished_at": c.finished_at,
                        "analyzed": c.analyzed, "candidates": c.candidates, "recommendations": c.recommendations, "message": c.message} for c in cycles],
            "scheduler_errors": request.app.state.scheduler.errors,
            "engine_state": request.app.state.engine.state,
        })


@router.get("/audit")
def audit(request: Request, limit: int = 200):
    with request.app.state.db.session() as s:
        rows = s.scalars(select(AuditLog).order_by(desc(AuditLog.id)).limit(limit)).all()
        return _clean([{"id": a.id, "at": a.at, "key": a.key, "old_value": a.old_value, "new_value": a.new_value, "actor": a.actor} for a in rows])


async def _set_paused(request: Request, paused: bool) -> dict:
    request.app.state.runtime.set("monitoring.paused", paused, actor="usuario")
    request.app.state.market.log_event("info", "controle", "Monitoramento pausado" if paused else "Monitoramento retomado")
    await request.app.state.ws.broadcast({"type": "settings", "data": {"monitoring.paused": paused}})
    return {"paused": paused}


@router.post("/control/pause")
async def pause(request: Request):
    return await _set_paused(request, True)


@router.post("/control/resume")
async def resume(request: Request):
    return await _set_paused(request, False)


@router.post("/control/scan")
async def scan(request: Request):
    asyncio.get_running_loop().create_task(request.app.state.engine.run_cycle("full", "manual"))
    return {"started": True}


@router.get("/notifications")
def notifications(request: Request, limit: int = 100):
    with request.app.state.db.session() as s:
        rows = s.scalars(select(Notification).order_by(desc(Notification.created_at)).limit(limit)).all()
        return _clean([{"id": n.id, "created_at": n.created_at, "kind": n.kind, "severity": n.severity, "title": n.title,
                        "body": n.body, "data": n.data, "read": n.read} for n in rows])


@router.post("/notifications/read")
def notifications_read(request: Request):
    with request.app.state.db.session() as s:
        for n in s.scalars(select(Notification).where(Notification.read.is_(False))):
            n.read = True
    return {"ok": True}
