"""Shared fixtures: point every test at an isolated, freshly migrated
SQLite file and hand out a FastAPI TestClient bound to it.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import dehoarder.db.session as db_session
import dehoarder.jobs.runner as runner
from dehoarder.config import DATA_DIR, settings
from dehoarder.db.migrate import migrate


@pytest.fixture(autouse=True)
def shops_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test gets its own copy of the registry (learning writes to it)
    and no OpenRouter key, so nothing can reach the network by accident."""
    path = tmp_path / "shops.yaml"
    shutil.copy(DATA_DIR / "shops.yaml", path)
    monkeypatch.setattr(settings, "shops_file", path)
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    return path


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
