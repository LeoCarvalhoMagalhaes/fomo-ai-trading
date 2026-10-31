from datetime import timedelta

from sqlalchemy import select

from app.db.models import Notification
from app.db.session import Database
from app.notify.channels import TelegramChannel
from app.notify.hub import Notifier
from tests.conftest import NOW


class Recorder:
    name = "teste"

    def __init__(self):
        self.sent = []

    def enabled(self) -> bool:
        return True

    async def send(self, n: dict) -> None:
        self.sent.append(n)


class Broken(Recorder):
    async def send(self, n: dict) -> None:
        raise RuntimeError("falhou")


def make():
    db = Database("sqlite:///:memory:")
    rec = Recorder()
    return db, rec, Notifier(db, [Broken(), rec], dedupe_minutes=30)


async def test_notification_is_stored_and_sent_even_if_a_channel_fails():
    db, rec, n = make()
    assert await n.notify("oportunidade", "rec:1", "Título", "Corpo", now=NOW)
    assert len(rec.sent) == 1
    with db.session() as s:
        assert len(s.scalars(select(Notification)).all()) == 1


async def test_duplicate_within_30min_suppressed():
    db, rec, n = make()
    await n.notify("oportunidade", "k", "T", "B", now=NOW)
    assert not await n.notify("oportunidade", "k", "T", "B", now=NOW + timedelta(minutes=29))
    assert await n.notify("oportunidade", "k", "T", "B", now=NOW + timedelta(minutes=31))
    assert len(rec.sent) == 2


async def test_relevant_change_bypasses_dedupe():
    db, rec, n = make()
    await n.notify("oportunidade", "k", "T", "B", now=NOW)
    assert await n.notify("oportunidade", "k", "T", "B2", now=NOW + timedelta(minutes=1), relevant_change=True)


def test_telegram_disabled_without_config():
    assert not TelegramChannel(None, None, client=None).enabled()
    assert not TelegramChannel("tok", None, client=None).enabled()
    assert TelegramChannel("tok", "123", client=None).enabled()
