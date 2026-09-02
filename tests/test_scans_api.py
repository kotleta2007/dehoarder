"""POST /api/v1/scans: tab list from the extension becomes a scan + tabs."""

from __future__ import annotations

from fastapi.testclient import TestClient

import dehoarder.db.session as db_session
from dehoarder.db.models import Scan, Tab


def test_create_scan_persists_scan_and_tabs(client: TestClient) -> None:
    payload = {
        "tabs": [
            {
                "windowId": 1,
                "id": 10,
                "url": "https://www.amazon.de/dp/XYZ",
                "title": "Some Book — Amazon.de",
                "discarded": False,
                "lastAccessed": 1_700_000_000_000,
            },
            {
                "windowId": 1,
                "id": 11,
                "url": "https://bookvoed.ru/product/123",
                "title": None,
                "discarded": True,
                "lastAccessed": None,
            },
        ]
    }

    response = client.post("/api/v1/scans", json=payload)
    assert response.status_code == 201
    body = response.json()

    assert body["source"] == "extension"
    assert body["tab_count"] == 2
    assert len(body["tabs"]) == 2

    by_url = {t["url"]: t for t in body["tabs"]}
    assert by_url["https://www.amazon.de/dp/XYZ"]["domain"] == "amazon.de"
    assert by_url["https://bookvoed.ru/product/123"]["domain"] == "bookvoed.ru"
    assert all(t["decision"] == "pending" for t in body["tabs"])

    with db_session.SessionLocal() as session:
        assert session.query(Scan).count() == 1
        assert session.query(Tab).count() == 2
        scan = session.query(Scan).one()
        assert scan.tab_count == 2


def test_create_scan_with_no_tabs(client: TestClient) -> None:
    response = client.post("/api/v1/scans", json={"tabs": []})
    assert response.status_code == 201
    body = response.json()
    assert body["tab_count"] == 0
    assert body["tabs"] == []
