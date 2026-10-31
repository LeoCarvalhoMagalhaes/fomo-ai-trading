from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.db.models import AuditLog, Recommendation, Token
from app.db.models import utcnow
from app.main import create_app


@pytest.fixture
def client():
    app = create_app(start_background=False, db_url="sqlite:///:memory:")
    with TestClient(app) as c:
        yield c


def add_rec(app):
    now = utcnow()
    with app.state.db.session() as s:
        t = Token(chain="solana", address="ADDR", symbol="ABC", name="Abc", category="established")
        s.add(t)
        s.flush()
        r = Recommendation(token_id=t.id, strategy="uptrend_momentum", category="established", analysis_at=now,
                           created_at=now, expires_at=now + timedelta(minutes=10), price_observed=1.0, amount_usd=7.0,
                           entry_low=0.995, entry_high=1.01, stop=0.9, target1=1.25, target2=1.4, score=86.0,
                           payload={"token": "ABC"}, text="TOKEN: ABC")
        s.add(r)
        s.flush()
        return r.id


def test_dashboard_shape(client):
    d = client.get("/api/dashboard").json()
    for key in ("capital", "mode", "books", "best_opportunity", "top_scores", "new_tokens", "market_regime",
                "last_cycle", "next_full_at", "providers", "alerts", "state", "tiers", "message"):
        assert key in d
    assert d["capital"] == 50 and d["mode"] == "SIM"
    assert d["books"]["SIM"]["available"] == 50
    assert d["message"].startswith("SEM OPERAÇÃO RECOMENDADA")
    # alvo mínimo exigido pelas regras = 6,25× o custo (stop ≥ 2,5× custo e alvo em 2,5R)
    sol = d["min_target_example"]["solana"]
    assert abs(sol - 6.25 * d["round_trip_example"]["solana"]) < 1e-6


def test_execute_triggers_full_cycle(client):
    rec_id = add_rec(client.app)
    r = client.post(f"/api/recommendations/{rec_id}/executed", json={"price": 1.002, "amount_usd": 7.0, "fee_usd": 0.5})
    assert r.status_code == 200, r.text
    assert client.app.state.engine.last_trigger == "execucao"
    trades = client.get("/api/trades?ledger=REAL").json()
    assert len(trades) == 1 and trades[0]["entry_price"] == 1.002
    assert client.get(f"/api/recommendations/{rec_id}").json()["status"] == "EXECUTADA"


def test_ignore_recommendation(client):
    rec_id = add_rec(client.app)
    assert client.post(f"/api/recommendations/{rec_id}/ignored").status_code == 200
    assert client.get(f"/api/recommendations/{rec_id}").json()["status"] == "IGNORADA"


def test_settings_put_audits(client):
    r = client.put("/api/settings", json={"changes": {"risk.max_exposure_usd": 12}})
    assert r.status_code == 200, r.text
    assert client.get("/api/settings").json()["values"]["risk.max_exposure_usd"] == 12
    audit = client.get("/api/audit").json()
    assert audit[0]["key"] == "risk.max_exposure_usd" and audit[0]["new_value"] == 12


def test_invalid_settings_rejected(client):
    assert client.put("/api/settings", json={"changes": {"risk.min_reserve_usd": 60}}).status_code == 400
    assert client.put("/api/settings", json={"changes": {"risk.established_min_usd": 20}}).status_code == 400
    assert client.put("/api/settings", json={"changes": {"mode": "OUTRO"}}).status_code == 400
    assert client.put("/api/settings", json={"changes": {"nao.existe": 1}}).status_code == 400
    assert client.put("/api/settings", json={"changes": {"risk.max_daily_loss_usd": -1}}).status_code == 400
    with client.app.state.db.session() as s:
        assert s.query(AuditLog).count() == 0


def test_manual_trade_and_close(client):
    r = client.post("/api/trades", json={"ledger": "REAL", "chain": "solana", "address": "NOVO", "symbol": "NV",
                                          "amount_usd": 5, "price": 2.0, "fee_usd": 0.5, "category": "new"})
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    r = client.post(f"/api/trades/{tid}/close", json={"price": 2.2, "fee_usd": 0.5})
    assert r.status_code == 200
    assert abs(r.json()["pnl_usd"] - (0.5 - 1.0)) < 1e-9
    p = client.get("/api/portfolio/REAL").json()
    assert p["metrics"]["n"] == 1 and abs(p["realized_pnl"] + 0.5) < 1e-9


def test_pause_resume(client):
    assert client.post("/api/control/pause").json()["paused"] is True
    assert client.get("/api/settings").json()["values"]["monitoring.paused"] is True
    assert client.post("/api/control/resume").json()["paused"] is False


def test_providers_and_logs(client):
    prov = client.get("/api/providers").json()
    assert {p["name"] for p in prov["providers"]} == {"dexscreener", "geckoterminal", "goplus"}
    assert prov["budgets"]["geckoterminal"] == 6
    assert client.get("/api/logs").status_code == 200


def test_stats_shape(client):
    st = client.get("/api/stats").json()
    assert {"SIM", "REAL", "filtros", "backtest", "estrategias"} <= set(st)
    assert len(st["estrategias"]) == 6


def test_cross_origin_post_rejected(client):
    r = client.post("/api/control/pause", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert client.post("/api/control/pause", headers={"Origin": "http://127.0.0.1:8765"}).status_code == 200
    assert client.post("/api/control/resume").status_code == 200  # sem Origin (ferramentas locais)
