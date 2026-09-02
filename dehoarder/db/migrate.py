"""Schema creation and version bookkeeping.

No Alembic: `migrate()` creates any missing tables via `create_all()` and
makes sure the single `schema_version` row reflects `CURRENT_VERSION`.
Re-running against an up-to-date database is a no-op.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import Engine

from dehoarder.db.models import Base, SchemaVersion
from dehoarder.db.session import SessionLocal
from dehoarder.db.session import engine as default_engine

CURRENT_VERSION = 1


def migrate(target_engine: Engine | None = None) -> None:
    target_engine = target_engine or default_engine
    Base.metadata.create_all(target_engine)

    with SessionLocal(bind=target_engine) as session:
        row = session.execute(select(SchemaVersion)).scalar_one_or_none()
        if row is None:
            session.add(SchemaVersion(version=CURRENT_VERSION))
            session.commit()
        elif row.version != CURRENT_VERSION:
            row.version = CURRENT_VERSION
            session.commit()


def init_db(target_engine: Engine | None = None) -> None:
    migrate(target_engine)
