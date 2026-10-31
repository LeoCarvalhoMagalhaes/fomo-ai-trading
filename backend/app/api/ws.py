import json
import logging

from fastapi import WebSocket

log = logging.getLogger(__name__)


class WSManager:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def broadcast(self, message: dict) -> None:
        text = json.dumps(message, default=str, ensure_ascii=False)
        for ws in list(self.clients):
            try:
                await ws.send_text(text)
            except Exception:
                self.disconnect(ws)
