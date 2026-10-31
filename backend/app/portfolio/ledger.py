"""Livros SIM (simulação) e REAL (operações informadas pelo usuário), sempre separados."""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Recommendation, Token, Trade
from app.risk.manager import BookState, OpenPosition, RiskLimits

LEDGERS = ("SIM", "REAL")


def _check_ledger(ledger: str) -> None:
    if ledger not in LEDGERS:
        raise ValueError(f"livro inválido: {ledger}")


def realized_pnl(amount: float, entry: float, exit_: float, fees: float) -> float:
    return amount * (exit_ / entry - 1) - fees


def manual_limit_flags(book: BookState, limits: RiskLimits, amount: float, category: str | None) -> list[str]:
    flags = []
    cat_max = limits.new_max_usd if category == "new" else limits.established_max_usd
    if amount > cat_max:
        flags.append(f"Valor de US$ {amount:.2f} acima do máximo por operação (US$ {cat_max:.2f})")
    if book.exposure + amount > limits.max_exposure_usd:
        flags.append(f"A exposição total passa a US$ {book.exposure + amount:.2f} (limite US$ {limits.max_exposure_usd:.2f})")
    if category == "new" and book.new_exposure + amount > limits.max_new_exposure_usd:
        flags.append(f"A exposição em tokens novos passa de US$ {limits.max_new_exposure_usd:.2f}")
    if book.capital_current - book.exposure - amount < limits.min_reserve_usd:
        flags.append(f"Reserva mínima de US$ {limits.min_reserve_usd:.2f} violada")
    if book.day_realized_pnl <= -limits.max_daily_loss_usd:
        flags.append("Operação aberta depois de atingido o limite de perda diária")
    return flags


def open_trade(
    s: Session,
    ledger: str,
    token_id: int,
    amount_usd: float,
    entry_price: float,
    fee_usd: float,
    executed_at: datetime,
    *,
    limits: RiskLimits,
    now: datetime,
    recommendation_id: int | None = None,
    strategy: str | None = None,
    category: str | None = None,
    stop: float | None = None,
    target1: float | None = None,
    target2: float | None = None,
    note: str = "",
) -> Trade:
    _check_ledger(ledger)
    if amount_usd <= 0 or entry_price <= 0 or fee_usd < 0:
        raise ValueError("valor, preço e taxa precisam ser positivos")
    book = book_state(s, ledger, now, limits)
    trade = Trade(
        ledger=ledger, token_id=token_id, recommendation_id=recommendation_id, strategy=strategy, category=category,
        amount_usd=amount_usd, entry_price=entry_price, entry_fee_usd=fee_usd, executed_at=executed_at,
        stop=stop, target1=target1, target2=target2, note=note,
        limit_flags=manual_limit_flags(book, limits, amount_usd, category), alerts_sent=[],
    )
    s.add(trade)
    s.flush()
    return trade


def close_trade(s: Session, trade_id: int, exit_price: float, fee_usd: float, closed_at: datetime, reason: str) -> Trade:
    trade = s.get(Trade, trade_id)
    if trade is None or trade.status != "OPEN":
        raise ValueError("operação inexistente ou já encerrada")
    if exit_price <= 0 or fee_usd < 0:
        raise ValueError("preço e taxa inválidos")
    trade.exit_price = exit_price
    trade.exit_fee_usd = fee_usd
    trade.closed_at = closed_at
    trade.close_reason = reason
    trade.status = "CLOSED"
    trade.pnl_usd = realized_pnl(trade.amount_usd, trade.entry_price, exit_price, trade.entry_fee_usd + fee_usd)
    s.flush()
    return trade


def book_state(s: Session, ledger: str, now: datetime, limits: RiskLimits, paused: bool = False) -> BookState:
    _check_ledger(ledger)
    open_rows = s.execute(
        select(Trade, Token.address).join(Token, Token.id == Trade.token_id).where(Trade.ledger == ledger, Trade.status == "OPEN")
    ).all()
    closed = s.scalars(
        select(Trade).where(Trade.ledger == ledger, Trade.status == "CLOSED").order_by(Trade.closed_at.desc())
    ).all()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    streak = 0
    last_loss_at = None
    for t in closed:
        if (t.pnl_usd or 0) < 0:
            streak += 1
            last_loss_at = last_loss_at or t.closed_at
        else:
            break
    recent = s.execute(
        select(Token.address, Recommendation.strategy, Recommendation.created_at)
        .join(Token, Token.id == Recommendation.token_id)
        .where(Recommendation.created_at >= now - timedelta(minutes=limits.dedupe_minutes))
    ).all()
    return BookState(
        capital_initial=limits.capital_usd,
        realized_pnl=sum(t.pnl_usd or 0 for t in closed),
        open_positions=[OpenPosition(addr, t.category or "established", t.amount_usd) for t, addr in open_rows],
        day_realized_pnl=sum(t.pnl_usd or 0 for t in closed if t.closed_at >= day_start),
        consecutive_losses=streak,
        last_loss_at=last_loss_at,
        recent_recs=[(a, st, at) for a, st, at in recent],
        paused=paused,
    )
