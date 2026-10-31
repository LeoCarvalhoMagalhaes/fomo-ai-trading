"""Central de notificações: grava, deduplica e distribui para os canais habilitados."""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models import Notification
from app.db.session import Database

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, db: Database, channels: list, dedupe_minutes: float = 30):
        self.db = db
        self.channels = channels
        self.dedupe_minutes = dedupe_minutes

    async def notify(
        self,
        kind: str,
        key: str,
        title: str,
        body: str,
        severity: str = "info",
        data: dict | None = None,
        relevant_change: bool = False,
        now: datetime | None = None,
    ) -> bool:
        now = now or datetime.now(timezone.utc)
        with self.db.session() as s:
            if not relevant_change:
                recent = s.scalars(
                    select(Notification.id).where(
                        Notification.key == key,
                        Notification.created_at > now - timedelta(minutes=self.dedupe_minutes),
                    ).limit(1)
                ).first()
                if recent is not None:
                    return False
            row = Notification(created_at=now, key=key, kind=kind, severity=severity, title=title, body=body, data=data)
            s.add(row)
            s.flush()
            payload = {"id": row.id, "created_at": now.isoformat(), "key": key, "kind": kind, "severity": severity,
                       "title": title, "body": body, "data": data, "read": False}
        for ch in self.channels:
            try:
                if ch.enabled():
                    await ch.send(payload)
            except Exception as exc:  # um canal com defeito não pode derrubar os outros
                log.warning("canal de notificação %s falhou: %s", getattr(ch, "name", ch), exc)
        return True
