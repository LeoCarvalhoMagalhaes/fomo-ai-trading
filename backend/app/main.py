"""Aplicação FastAPI: monta provedores, serviços, tarefas periódicas, API e a interface compilada.

Execução: uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8765
"""
import logging
import logging.handlers
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.api.ws import WSManager
from app.collector.scheduler import Scheduler
from app.collector.service import MarketService
from app.config import ROOT, Settings
from app.db.runtime_settings import RuntimeSettings
from app.db.session import Database
from app.notify.channels import InAppChannel, TelegramChannel, WindowsToastChannel
from app.notify.hub import Notifier
from app.providers.base import ProviderHealth, RateLimiter
from app.providers.dexscreener import DexScreener
from app.providers.geckoterminal import GeckoTerminal
from app.providers.goplus import GoPlus
from app.recommend.engine import AnalysisEngine

FRONTEND_DIST = ROOT / "frontend" / "dist"
USER_AGENT = "fomo-ai-trading/0.1 (ferramenta local de uso pessoal)"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        import json

        return json.dumps({"t": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "nivel": record.levelname,
                           "modulo": record.name, "msg": record.getMessage(),
                           **({"exc": self.formatException(record.exc_info)} if record.exc_info else {})}, ensure_ascii=False)


def setup_logging(data_dir: Path) -> None:
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if any(getattr(h, "_fomo", False) for h in root.handlers):
        return
    handler = logging.handlers.RotatingFileHandler(log_dir / "app.jsonl", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(JsonFormatter())
    handler._fomo = True
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def create_app(start_background: bool = True, db_url: str | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    if db_url:
        settings.db_url = db_url
    db = Database(settings.database_url())
    runtime = RuntimeSettings(db)
    ws = WSManager()
    client = httpx.AsyncClient(headers={"User-Agent": USER_AGENT})

    dex = DexScreener(client, RateLimiter(settings.dex_rpm), ProviderHealth("dexscreener"))
    gecko = GeckoTerminal(client, RateLimiter(settings.gecko_rpm), ProviderHealth("geckoterminal"), settings.coingecko_demo_key)
    goplus = GoPlus(client, RateLimiter(settings.goplus_rpm), ProviderHealth("goplus"))
    notifier = Notifier(
        db,
        [InAppChannel(ws.broadcast), WindowsToastChannel(lambda: bool(runtime.get("notify.windows_toast"))),
         TelegramChannel(settings.telegram_bot_token, settings.telegram_chat_id, client)],
        dedupe_minutes=float(runtime.get("notify.dedupe_minutes")),
    )
    market = MarketService(db, dex, gecko, goplus, runtime)
    engine = AnalysisEngine(db, market, notifier, runtime, ws.broadcast)
    scheduler = Scheduler(market, engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_background:
            setup_logging(settings.data_dir)
            market.log_event("info", "sistema", "Aplicação iniciada")
            scheduler.start()
        yield
        await scheduler.stop()
        await client.aclose()

    app = FastAPI(title="FOMO AI Trading Intelligence", lifespan=lifespan)
    allowed_origins = {f"http://{h}:{p}" for h in ("127.0.0.1", "localhost") for p in (settings.port, 5320)}

    @app.middleware("http")
    async def same_origin_only(request: Request, call_next):
        # Impede que outras páginas abertas no navegador alterem dados locais (CSRF)
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin not in allowed_origins:
            return JSONResponse({"detail": "Origem não permitida"}, status_code=403)
        return await call_next(request)
    app.state.settings = settings
    app.state.db = db
    app.state.runtime = runtime
    app.state.ws = ws
    app.state.market = market
    app.state.engine = engine
    app.state.notifier = notifier
    app.state.scheduler = scheduler
    app.include_router(router)

    @app.websocket("/ws")
    async def websocket(sock: WebSocket):
        origin = sock.headers.get("origin")
        if origin and origin not in allowed_origins:
            await sock.close(code=1008)
            return
        await ws.connect(sock)
        try:
            while True:
                await sock.receive_text()
        except WebSocketDisconnect:
            ws.disconnect(sock)

    if FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            file = FRONTEND_DIST / path
            if path and file.is_file() and FRONTEND_DIST in file.resolve().parents:
                return FileResponse(file)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app
