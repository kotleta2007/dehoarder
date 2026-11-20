"""POST /api/v1/scans/snss: fallback scan from a Chromium SNSS session
file, driven by a fixture Thorium directory (`Local State` + a real
`Sessions/Session_*` built the same way as the synthetic fixture in
tests/test_snss.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import dehoarder.db.session as db_session
from dehoarder.config import settings
from dehoarder.db.models import Scan, Tab

FIXTURE_THORIUM_DIR = Path(__file__).parent / "fixtures" / "thorium_with_session"


@pytest.fixture(autouse=True)
def _thorium_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "thorium_dir", FIXTURE_THORIUM_DIR)


def test_scan_snss_uses_current_profile_by_default(client: TestClient) -> None:
    response = client.post("/api/v1/scans/snss", json={})
    assert response.status_code == 201
    body = response.json()

    assert body["source"] == "snss"
    assert body["profile_name"] == "Test Profile"
    assert body["tab_count"] == 2
    urls = {t["url"] for t in body["tabs"]}
    assert urls == {"https://bookvoed.ru/product/fixture", "https://www.amazon.de/dp/FIXTURE"}
    assert {t["domain"] for t in body["tabs"]} == {"bookvoed.ru", "amazon.de"}

    with db_session.SessionLocal() as session:
        assert session.query(Scan).count() == 1
        assert session.query(Tab).count() == 2


def test_scan_snss_with_explicit_profile_name(client: TestClient) -> None:
    response = client.post("/api/v1/scans/snss", json={"profile_name": "Test Profile"})
    assert response.status_code == 201
    assert response.json()["tab_count"] == 2


def test_scan_snss_unknown_profile_is_404(client: TestClient) -> None:
    response = client.post("/api/v1/scans/snss", json={"profile_name": "Nope"})
    assert response.status_code == 404
