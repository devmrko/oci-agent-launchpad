from python_foundation.errors import AccessDenied
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Record


class DeskRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, key: str, owner: str, kind: str):
        row = self.session.get(Record, key)
        if row is None or row.owner != owner or row.kind != kind:
            raise AccessDenied()
        return row

    def add(self, key: str, owner: str, kind: str, data: dict):
        row = Record(id=key, owner=owner, kind=kind, data=data)
        self.session.add(row)
        return row

    def list(self, owner: str, kind: str):
        return list(self.session.scalars(select(Record).where(Record.owner == owner, Record.kind == kind)))
