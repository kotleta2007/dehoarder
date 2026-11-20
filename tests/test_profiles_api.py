"""GET /api/v1/profiles: lists Thorium profiles for the SNSS dropdown."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dehoarder.config import settings

FIXTURE_THORIUM_DIR = Path(__file__).parent / "fixtures" / "thorium_profiles"


def test_get_profiles_marks_the_last_used_one_current(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "thorium_dir", FIXTURE_THORIUM_DIR)

    response = client.get("/api/v1/profiles")
    assert response.status_code == 200
    profiles = {p["display_name"]: p for p in response.json()}

    assert set(profiles) == {"Mark", "Work", "Books"}
    assert profiles["Work"]["current"] is True
    assert profiles["Mark"]["current"] is False


def test_get_profiles_empty_when_no_local_state(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "thorium_dir", tmp_path / "nonexistent")

    response = client.get("/api/v1/profiles")
    assert response.status_code == 200
    assert response.json() == []
