"""Esquema SQLite. Horários sempre em UTC com fuso."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, TypeDecorator, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """SQLite não guarda fuso: grava em UTC sem fuso e devolve com fuso UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("datetime sem fuso horário")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


class Base(DeclarativeBase):
    pass


class Token(Base):
    __tablename__ = "tokens"
    __table_args__ = (UniqueConstraint("chain", "address"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    chain: Mapped[str] = mapped_column(String(20))
    address: Mapped[str] = mapped_column(String(80))
    symbol: Mapped[str] = mapped_column(String(64), default="")
    name: Mapped[str] = mapped_column(String(128), default="")
    pair_address: Mapped[str | None] = mapped_column(String(80))
    dex_id: Mapped[str | None] = mapped_column(String(40))
    pair_created_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    category: Mapped[str | None] = mapped_column(String(20))
    tier: Mapped[int] = mapped_column(Integer, default=1)
    classification: Mapped[str | None] = mapped_column(String(1))
    class_reasons: Mapped[list | None] = mapped_column(JSON)
    discovered_via: Mapped[str | None] = mapped_column(String(40))
    first_seen: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Snapshot(Base):
    __tablename__ = "snapshots"
    __table_args__ = (Index("ix_snap_token_time", "token_id", "observed_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id"))
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    source: Mapped[str] = mapped_column(String(30))
    price_usd: Mapped[float | None] = mapped_column(Float)
    liquidity_usd: Mapped[float | None] = mapped_column(Float)
    reliability: Mapped[float] = mapped_column(Float, default=1.0)
    data: Mapped[dict] = mapped_column(JSON)  # PairSnapshot completo


class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (UniqueConstraint("token_id", "tf", "ts"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id"))
    tf: Mapped[str] = mapped_column(String(5))
    ts: Mapped[datetime] = mapped_column(UTCDateTime)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(30))


class SecurityReportRow(Base):
    __tablename__ = "security_reports"
    __table_args__ = (Index("ix_sec_token_time", "token_id", "observed_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id"))
    source: Mapped[str] = mapped_column(String(30))
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    data: Mapped[dict] = mapped_column(JSON)


class Cycle(Base):
    __tablename__ = "cycles"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))
    trigger: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    analyzed: Mapped[int] = mapped_column(Integer, default=0)
    candidates: Mapped[int] = mapped_column(Integer, default=0)
    recommendations: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")


class Evaluation(Base):
    """Toda avaliação (recomendada ou rejeitada) fica gravada para medir os filtros depois."""

    __tablename__ = "evaluations"
    __table_args__ = (Index("ix_eval_time", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey("cycles.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id"))
    strategy: Mapped[str | None] = mapped_column(String(40))
    category: Mapped[str | None] = mapped_column(String(20))
    score: Mapped[float | None] = mapped_column(Float)
    band: Mapped[str | None] = mapped_column(String(30))
    components: Mapped[list | None] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(String(20))  # RECOMENDADA | REJEITADA
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    price: Mapped[float | None] = mapped_column(Float)
    stop: Mapped[float | None] = mapped_column(Float)
    target1: Mapped[float | None] = mapped_column(Float)
    outcome_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    outcome_price: Mapped[float | None] = mapped_column(Float)
    outcome_return_pct: Mapped[float | None] = mapped_column(Float)
    outcome_hit: Mapped[str | None] = mapped_column(String(10))  # alvo1 | stop | tempo


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id"))
    evaluation_id: Mapped[int | None] = mapped_column(ForeignKey("evaluations.id"))
    strategy: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(12), default="ATIVA")  # ATIVA|EXECUTADA|IGNORADA|EXPIRADA
    analysis_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    status_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status_reason: Mapped[str | None] = mapped_column(Text)
    price_observed: Mapped[float] = mapped_column(Float)
    amount_usd: Mapped[float] = mapped_column(Float)
    entry_low: Mapped[float] = mapped_column(Float)
    entry_high: Mapped[float] = mapped_column(Float)
    stop: Mapped[float] = mapped_column(Float)
    target1: Mapped[float] = mapped_column(Float)
    target2: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSON)
    text: Mapped[str] = mapped_column(Text)


class Trade(Base):
    __tablename__ = "trades"
    id: Mapped[int] = mapped_column(primary_key=True)
    ledger: Mapped[str] = mapped_column(String(4))  # SIM | REAL
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id"))
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("recommendations.id"))
    strategy: Mapped[str | None] = mapped_column(String(40))
    category: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(8), default="OPEN")  # OPEN | CLOSED
    amount_usd: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    entry_fee_usd: Mapped[float] = mapped_column(Float, default=0.0)
    executed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    stop: Mapped[float | None] = mapped_column(Float)
    target1: Mapped[float | None] = mapped_column(Float)
    target2: Mapped[float | None] = mapped_column(Float)
    exit_price: Mapped[float | None] = mapped_column(Float)
    exit_fee_usd: Mapped[float | None] = mapped_column(Float)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    close_reason: Mapped[str | None] = mapped_column(String(40))
    pnl_usd: Mapped[float | None] = mapped_column(Float)
    last_price: Mapped[float | None] = mapped_column(Float)
    last_price_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    alerts_sent: Mapped[list] = mapped_column(JSON, default=list)
    limit_flags: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(Text, default="")


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_event_time", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    level: Mapped[str] = mapped_column(String(8))
    kind: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict | None] = mapped_column(JSON)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notif_key_time", "key", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    key: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    data: Mapped[dict | None] = mapped_column(JSON)
    read: Mapped[bool] = mapped_column(Boolean, default=False)


class SettingRow(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[object] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    key: Mapped[str] = mapped_column(String(80))
    old_value: Mapped[object] = mapped_column(JSON)
    new_value: Mapped[object] = mapped_column(JSON)
    actor: Mapped[str] = mapped_column(String(40))
