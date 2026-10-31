import json
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
