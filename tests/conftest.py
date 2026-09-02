"""Shared fixtures: point every test at an isolated, freshly migrated
SQLite file and hand out a FastAPI TestClient bound to it.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import dehoarder.db.session as db_session
import dehoarder.jobs.runner as runner
from dehoarder.db.migrate import migrate


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path: Path) -> Iterator[None]:
    db_session.configure(str(tmp_path / "test.db"))
    migrate(db_session.engine)
    runner.clear_registry()
    yield
    runner.clear_registry()


@pytest.fixture
def client() -> TestClient:
    from dehoarder.api.app import app

    return TestClient(app)
