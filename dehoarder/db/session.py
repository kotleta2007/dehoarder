"""Engine and session factory.

`sqlite3` does not honour PRAGMAs from the connection URL, so WAL mode and
foreign-key enforcement are set on every new DBAPI connection via a
`connect` event listener instead.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from sqlite3 import Connection as SQLite3Connection

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from dehoarder.config import settings


def make_engine(db_path: str | None = None) -> Engine:
    path = db_path if db_path is not None else str(settings.db_path)
    engine = create_engine(f"sqlite:///{path}", future=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: object, connection_record: object) -> None:
        if not isinstance(dbapi_connection, SQLite3Connection):
            return
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def get_session(bind: Engine | None = None) -> Iterator[Session]:
    session = SessionLocal(bind=bind) if bind is not None else SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
