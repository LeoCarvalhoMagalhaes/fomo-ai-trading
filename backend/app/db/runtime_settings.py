"""Configurações editáveis em tempo de execução, com auditoria de cada alteração."""
from sqlalchemy import select

from app.config import DEFAULT_RUNTIME
from app.db.models import AuditLog, SettingRow, utcnow
from app.db.session import Database


class RuntimeSettings:
    def __init__(self, db: Database):
        self.db = db

    def all(self) -> dict:
        values = dict(DEFAULT_RUNTIME)
        with self.db.session() as s:
            for row in s.scalars(select(SettingRow)):
                if row.key in values:
                    values[row.key] = row.value
        return values

    def get(self, key: str):
        if key not in DEFAULT_RUNTIME:
            raise KeyError(key)
        with self.db.session() as s:
            row = s.get(SettingRow, key)
            return row.value if row else DEFAULT_RUNTIME[key]

    def set(self, key: str, value, actor: str) -> None:
        if key not in DEFAULT_RUNTIME:
            raise KeyError(key)
        old = self.get(key)
        if old == value:
            return
        with self.db.session() as s:
            row = s.get(SettingRow, key)
            if row is None:
                s.add(SettingRow(key=key, value=value, updated_at=utcnow()))
            else:
                row.value = value
                row.updated_at = utcnow()
            s.add(AuditLog(key=key, old_value=old, new_value=value, actor=actor))
