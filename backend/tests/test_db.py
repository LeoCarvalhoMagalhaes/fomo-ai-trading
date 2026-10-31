from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models import AuditLog, Candle as CandleRow, Token
from app.db.runtime_settings import RuntimeSettings
from app.db.session import Database
from app.domain import Candle


def make_db():
    return Database("sqlite:///:memory:")


def test_settings_change_is_audited():
    db = make_db()
    rs = RuntimeSettings(db)
    assert rs.get("risk.max_exposure_usd") == 15
    rs.set("risk.max_exposure_usd", 12, actor="usuario")
    assert rs.get("risk.max_exposure_usd") == 12
    with db.session() as s:
        rows = s.scalars(select(AuditLog)).all()
    assert len(rows) == 1
    assert (rows[0].key, rows[0].old_value, rows[0].new_value, rows[0].actor) == ("risk.max_exposure_usd", 15, 12, "usuario")
    assert rs.all()["risk.max_exposure_usd"] == 12


def test_settings_unknown_key_rejected():
    rs = RuntimeSettings(make_db())
    try:
        rs.set("nao.existe", 1, actor="usuario")
    except KeyError:
        return
    raise AssertionError("chave desconhecida deveria falhar")


def test_candle_unique_constraint():
    db = make_db()
    ts = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    with db.session() as s:
        tok = Token(chain="solana", address="X", symbol="X", name="X")
        s.add(tok)
        s.flush()
        tid = tok.id
    c1 = Candle(ts=ts, open=1, high=2, low=0.5, close=1.5, volume=10)
    c2 = Candle(ts=ts, open=1, high=3, low=0.5, close=2.5, volume=20)
    db.upsert_candles(tid, "5m", [c1], source="geckoterminal")
    db.upsert_candles(tid, "5m", [c2], source="geckoterminal")
    with db.session() as s:
        rows = s.scalars(select(CandleRow)).all()
    assert len(rows) == 1
    assert rows[0].close == 2.5
