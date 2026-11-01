"""Acesso por senha quando o app está online (FOMOAI_PASSWORD). Sem senha configurada, tudo fica aberto (uso local).

O navegador guarda só um token derivado da senha, nunca a senha. Trocar a senha invalida os tokens antigos.
"""
import hashlib
import hmac
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

PUBLIC_PATHS = {"/api/ping", "/api/health", "/api/auth", "/api/login"}
MAX_FAILURES_PER_MINUTE = 5

router = APIRouter(prefix="/api")


def token_for(password: str) -> str:
    return hmac.new(password.encode(), b"fomo-ai-session-v1", hashlib.sha256).hexdigest()


def token_ok(password: str | None, token: str | None) -> bool:
    if not password:
        return True
    return bool(token) and hmac.compare_digest(token, token_for(password))


def bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    return header[7:] if header.lower().startswith("bearer ") else None


class LoginBody(BaseModel):
    password: str


@router.get("/ping")
async def ping():
    """Para o monitor externo que mantém o servidor gratuito acordado; não consulta o banco."""
    return {"status": "ok"}


@router.get("/health")
def health(request: Request):
    try:
        with request.app.state.db.session() as s:
            s.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "erro"
    return {"status": "ok" if database == "ok" else "degraded", "database": database}


@router.get("/auth")
async def auth_status(request: Request):
    return {"required": bool(request.app.state.settings.password)}


@router.post("/login")
async def login(body: LoginBody, request: Request):
    password = request.app.state.settings.password
    if not password:
        return {"token": ""}
    who = request.client.host if request.client else "?"
    if not hasattr(request.app.state, "login_failures"):
        request.app.state.login_failures = defaultdict(deque)
    recent = request.app.state.login_failures[who]
    now = time.monotonic()
    while recent and now - recent[0] > 60:
        recent.popleft()
    if len(recent) >= MAX_FAILURES_PER_MINUTE:
        raise HTTPException(429, "Muitas tentativas. Espere um minuto.")
    if not hmac.compare_digest(body.password.encode(), password.encode()):
        recent.append(now)
        raise HTTPException(401, "Senha incorreta")
    recent.clear()
    return {"token": token_for(password)}
