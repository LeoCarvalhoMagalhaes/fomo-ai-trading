from datetime import datetime, timedelta
from typing import Literal

Category = Literal["established", "intermediate", "new"]

NEW_MAX_AGE = timedelta(hours=72)
ESTABLISHED_MIN_AGE = timedelta(days=7)
ESTABLISHED_MIN_LIQUIDITY = 250_000

LABELS = {"established": "Token estabelecido", "intermediate": "Token intermediário", "new": "Novo token"}


def categorize(pair_created_at: datetime | None, liquidity_usd: float | None, now: datetime) -> Category:
    """Spec 3.3. Idade desconhecida não pode ser tratada como estabelecida nem como nova: vira intermediário."""
    if pair_created_at is None:
        return "intermediate"
    age = now - pair_created_at
    if age < NEW_MAX_AGE:
        return "new"
    if age >= ESTABLISHED_MIN_AGE and (liquidity_usd or 0) >= ESTABLISHED_MIN_LIQUIDITY:
        return "established"
    return "intermediate"
