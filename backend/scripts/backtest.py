"""Roda o backtest sobre os candles gravados no banco local e imprime/salva o relatório.

Uso: .venv\Scripts\python scripts\backtest.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.backtest.report import backtest_from_db, filter_report, save_report  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db.models import Snapshot  # noqa: E402
from app.db.runtime_settings import RuntimeSettings  # noqa: E402
from app.db.session import Database  # noqa: E402


def main() -> None:
    settings = Settings()
    db = Database(settings.database_url())
    cfg = RuntimeSettings(db).all()
    liquidity = {}
    with db.session() as s:
        for row in s.scalars(select(Snapshot).order_by(Snapshot.observed_at)):
            if row.liquidity_usd:
                liquidity[row.token_id] = row.liquidity_usd
    report = {"backtest": backtest_from_db(db, cfg, liquidity), "filtros": filter_report(db)}
    path = save_report(report, settings.data_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(f"\nRelatório salvo em {path}")


if __name__ == "__main__":
    main()
