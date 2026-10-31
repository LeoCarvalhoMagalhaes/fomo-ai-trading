"""Canais de notificação: no app (WebSocket), Windows (toast) e Telegram (desligado sem configuração)."""
import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable

import httpx

log = logging.getLogger(__name__)


class InAppChannel:
    name = "app"

    def __init__(self, broadcast: Callable[[dict], Awaitable[None]]):
        self.broadcast = broadcast

    def enabled(self) -> bool:
        return True

    async def send(self, n: dict) -> None:
        await self.broadcast({"type": "notification", "data": n})


class WindowsToastChannel:
    name = "windows"

    def __init__(self, is_enabled: Callable[[], bool], app_id: str = "FOMO AI Trading Intelligence"):
        self.is_enabled = is_enabled
        self.app_id = app_id

    def enabled(self) -> bool:
        return sys.platform == "win32" and self.is_enabled()

    async def send(self, n: dict) -> None:
        if n.get("severity") not in ("alta", "critica"):
            return  # só eventos importantes viram toast, para não poluir a área de trabalho
        await asyncio.to_thread(self._show, n["title"], n["body"][:250])

    def _show(self, title: str, body: str) -> None:
        from winotify import Notification as Toast

        Toast(app_id=self.app_id, title=title, msg=body).show()


class TelegramChannel:
    """Integração futura opcional via Bot API oficial (core.telegram.org/bots/api). Exige token e chat_id no .env."""

    name = "telegram"

    def __init__(self, token: str | None, chat_id: str | None, client: httpx.AsyncClient | None):
        self.token = token
        self.chat_id = chat_id
        self.client = client

    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    async def send(self, n: dict) -> None:
        if n.get("severity") not in ("alta", "critica") or self.client is None:
            return
        await self.client.post(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            json={"chat_id": self.chat_id, "text": f"{n['title']}\n\n{n['body']}"[:4000]},
            timeout=15,
        )
