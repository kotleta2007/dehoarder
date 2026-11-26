"""Schema creation and version bookkeeping.

No Alembic: `migrate()` creates any missing tables via `create_all()`, then
runs the upgrade steps for changes `create_all()` cannot make to an existing
table (it never adds columns), and finally makes sure the single
`schema_version` row reflects `CURRENT_VERSION`. Every step checks the live
schema before acting, so re-running against an up-to-date database is a
no-op.
"""

from __future__ import annotations

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine

from dehoarder.db.models import Base, SchemaVersion
from dehoarder.db.session import SessionLocal
from dehoarder.db.session import engine as default_engine

CURRENT_VERSION = 2


def _columns(engine: Engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def _v2_llm_call_response(engine: Engine) -> None:
    """v2: `llm_call.response` (cached completion text) + index on prompt_hash."""
    if "response" not in _columns(engine, "llm_call"):
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE llm_call ADD COLUMN response TEXT"))
    with engine.begin() as conn:
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_llm_call_prompt_hash ON llm_call (prompt_hash)")
        )


UPGRADES = [_v2_llm_call_response]


def migrate(target_engine: Engine | None = None) -> None:
    target_engine = target_engine or default_engine
    Base.metadata.create_all(target_engine)
    for upgrade in UPGRADES:
        upgrade(target_engine)

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
