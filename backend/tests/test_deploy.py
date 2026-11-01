"""Publicação online: Postgres, senha de acesso, CORS do GitHub Pages, ping e limpeza de dados antigos."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from starlette.websockets import WebSocketDisconnect

from app.config import Settings
from app.db.models import Candle, Evaluation, Event, Notification, Snapshot, Token, utcnow
from app.db.retention import prune_old_data
from app.db.session import Database, normalize_db_url
from app.main import create_app
from tests.conftest import test_db_url

PAGES = "https://leocarvalhomagalhaes.github.io"


def make_client(**kw):
    settings = Settings(_env_file=None, **kw)
    return TestClient(create_app(start_background=False, db_url=test_db_url(), settings=settings))


def test_normalize_db_url():
    assert normalize_db_url("postgres://u:p@h/db?sslmode=require") == "postgresql+psycopg://u:p@h/db?sslmode=require"
    assert normalize_db_url("postgresql://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    assert normalize_db_url("sqlite:///:memory:") == "sqlite:///:memory:"


def test_ping_does_not_need_password_or_db():
    with make_client(password="segredo") as c:
        assert c.get("/api/ping").json() == {"status": "ok"}


def test_health_reports_database():
    with make_client() as c:
        body = c.get("/api/health").json()
        assert body["status"] == "ok" and body["database"] == "ok"


def test_password_required_when_set():
    with make_client(password="segredo") as c:
        assert c.get("/api/dashboard").status_code == 401
        assert c.post("/api/login", json={"password": "errada"}).status_code == 401
        token = c.post("/api/login", json={"password": "segredo"}).json()["token"]
        assert "segredo" not in token
        assert c.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        assert c.get("/api/dashboard", headers={"Authorization": "Bearer outro"}).status_code == 401


def test_auth_status_tells_frontend_whether_login_is_needed():
    with make_client() as c:
        assert c.get("/api/auth").json() == {"required": False}
    with make_client(password="segredo") as c:
        assert c.get("/api/auth").json() == {"required": True}


def test_login_attempts_are_limited():
    with make_client(password="segredo") as c:
        codes = [c.post("/api/login", json={"password": "x"}).status_code for _ in range(6)]
        assert codes[:5] == [401] * 5 and codes[5] == 429


def test_websocket_requires_token_when_password_set():
    with make_client(password="segredo") as c:
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect("/ws") as ws:
                ws.receive_text()
        token = c.post("/api/login", json={"password": "segredo"}).json()["token"]
        with c.websocket_connect(f"/ws?token={token}"):
            pass


def test_production_refuses_to_start_without_password():
    with pytest.raises(RuntimeError, match="FOMOAI_PASSWORD"):
        create_app(start_background=False, db_url=test_db_url(), settings=Settings(_env_file=None, env="production"))


def test_cors_allows_github_pages_origin():
    with make_client(cors_origins=PAGES) as c:
        pre = c.options("/api/control/pause", headers={
            "Origin": PAGES, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type"})
        assert pre.headers.get("access-control-allow-origin") == PAGES
        assert c.post("/api/control/pause", headers={"Origin": PAGES}).status_code == 200
        assert c.post("/api/control/pause", headers={"Origin": "https://evil.example"}).status_code == 403


def _seed(db: Database, now):
    with db.session() as s:
        t = Token(chain="solana", address="A", symbol="A", name="A", category="established")
        s.add(t)
        s.flush()
        for age in (timedelta(hours=1), timedelta(hours=72)):
            s.add(Snapshot(token_id=t.id, observed_at=now - age, price_usd=1.0, source="dexscreener", data={}))
            s.add(Candle(token_id=t.id, tf="5m", ts=now - age * 10, open=1, high=1, low=1, close=1, volume=0,
                         source="geckoterminal"))
            s.add(Event(level="info", kind="sistema", message="x", created_at=now - age * 20))
            s.add(Notification(key=f"k{age}", kind="sistema", severity="baixa", title="t", body="b",
                               created_at=now - age * 20))
        s.add(Evaluation(token_id=t.id, created_at=now - timedelta(days=90), decision="REJEITADA"))


def test_prune_old_data_keeps_recent_rows_and_evaluations():
    db = Database(test_db_url())
    now = utcnow()
    _seed(db, now)
    removed = prune_old_data(db, now, snapshots_hours=48, candles_days=14, logs_days=30)
    assert removed == {"snapshots": 1, "candles": 1, "events": 1, "notifications": 1}
    with db.session() as s:
        for model in (Snapshot, Candle, Event, Notification):
            assert s.scalar(select(func.count()).select_from(model)) == 1
        assert s.scalar(select(func.count()).select_from(Evaluation)) == 1  # resultados alimentam a calibração


def test_production_hides_api_docs():
    settings = Settings(_env_file=None, env="production", password="segredo")
    with TestClient(create_app(start_background=False, db_url=test_db_url(), settings=settings)) as c:
        # sem a documentação, esses caminhos caem na interface (ou em 404), nunca no esquema da API
        assert "swagger" not in c.get("/docs").text.lower()
        assert '"openapi"' not in c.get("/openapi.json").text


def test_github_pages_may_reach_the_server_on_this_pc():
    """Site público (GitHub Pages) chamando o servidor em 127.0.0.1: o Chrome pede licença de rede local."""
    with make_client(cors_origins=PAGES) as c:
        headers = {"Origin": PAGES, "Access-Control-Request-Method": "GET",
                   "Access-Control-Request-Private-Network": "true"}
        assert c.options("/api/dashboard", headers=headers).headers.get("access-control-allow-private-network") == "true"
        other = {**headers, "Origin": "https://evil.example"}
        assert c.options("/api/dashboard", headers=other).headers.get("access-control-allow-private-network") is None
