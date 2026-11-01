import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 31, 14, 0, tzinfo=timezone.utc)


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def now():
    return NOW


def test_db_url() -> str:
    """SQLite em memória; com TEST_DATABASE_URL, um Postgres zerado a cada chamada (a suíte toda roda nos dois)."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        return "sqlite:///:memory:"
    from sqlalchemy import create_engine

    from app.db.models import Base
    from app.db.session import normalize_db_url

    engine = create_engine(normalize_db_url(url))
    Base.metadata.drop_all(engine)
    engine.dispose()
    return url


test_db_url.__test__ = False  # não é um teste, apesar do nome
