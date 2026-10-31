"""Tarefas periódicas: atualização rápida (60 s), candles (contínuo), descoberta (15 min), varredura completa (60 min)."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.db.retention import prune_old_data

log = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, market, engine, quick_s=60, candles_s=30, discovery_s=900, full_s=3600, outcomes_s=300,
                 prune_s=3600):
        self.market = market
        self.engine = engine
        self.quick_s = quick_s
        self.candles_s = candles_s
        self.discovery_s = discovery_s
        self.full_s = full_s
        self.outcomes_s = outcomes_s
        self.prune_s = prune_s
        self.tasks: list[asyncio.Task] = []
        self.errors = 0

    def start(self) -> None:
        loops = {
            "rapido": (self._quick, self.quick_s),
            "candles": (self._candles, self.candles_s),
            "descoberta": (self._discovery, self.discovery_s),
            "completo": (self._full, self.full_s),
            "resultados": (self._outcomes, self.outcomes_s),
            "limpeza": (self._prune, self.prune_s),
        }
        self.tasks = [asyncio.create_task(self._loop(name, fn, every), name=name) for name, (fn, every) in loops.items()]

    async def stop(self) -> None:
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def _loop(self, name, fn, every) -> None:
        if name == "descoberta":
            await asyncio.sleep(every)  # a primeira descoberta já acontece na varredura completa inicial
        while True:
            try:
                await fn()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.errors += 1
                log.exception("tarefa %s falhou; continua na próxima rodada", name)
            await asyncio.sleep(every)

    async def _quick(self) -> None:
        await self.market.refresh_tier1()
        await self.engine.expire_recommendations()
        await self.engine.monitor_positions()
        await self.engine.run_cycle("quick", "agenda")

    async def _candles(self) -> None:
        await self.market.refresh_candles()

    async def _discovery(self) -> None:
        await self.market.discover(trending=False)

    async def _full(self) -> None:
        trigger = "inicio" if self.engine.next_full_at is None else "agenda"
        self.engine.next_full_at = datetime.now(timezone.utc) + timedelta(seconds=self.full_s)
        await self.engine.run_cycle("full", trigger)

    async def _outcomes(self) -> None:
        await self.engine.track_outcomes()

    async def _prune(self) -> None:
        rt = self.market.runtime
        removed = await asyncio.to_thread(
            prune_old_data, self.market.db, datetime.now(timezone.utc),
            float(rt.get("data.retention_snapshots_hours")), float(rt.get("data.retention_candles_days")),
            float(rt.get("data.retention_logs_days")))
        self.market.forget_stale_tokens()
        if any(removed.values()):
            log.info("limpeza de dados antigos: %s", removed)
