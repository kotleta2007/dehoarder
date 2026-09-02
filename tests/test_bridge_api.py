"""Bridge routes: the extension's hello handshake and its status."""

from __future__ import annotations

from fastapi.testclient import TestClient

import dehoarder.db.session as db_session
from dehoarder.db.models import Bridge


def test_status_before_any_hello(client: TestClient) -> None:
    response = client.get("/api/v1/bridge/status")
    assert response.status_code == 200
    assert response.json() == {
        "connected": False,
        "extension_id": None,
        "version": None,
        "last_seen": None,
    }


def test_hello_then_status(client: TestClient) -> None:
    hello = client.post("/api/v1/bridge/hello", json={"extension_id": "abc123", "version": "0.1.0"})
    assert hello.status_code == 204

    status = client.get("/api/v1/bridge/status")
    assert status.status_code == 200
    body = status.json()
    assert body["connected"] is True
    assert body["extension_id"] == "abc123"
    assert body["version"] == "0.1.0"
    assert body["last_seen"] is not None


def test_repeated_hello_updates_the_same_row(client: TestClient) -> None:
    client.post("/api/v1/bridge/hello", json={"extension_id": "abc123", "version": "0.1.0"})
    client.post("/api/v1/bridge/hello", json={"extension_id": "abc123", "version": "0.2.0"})

    body = client.get("/api/v1/bridge/status").json()
    assert body["version"] == "0.2.0"

    with db_session.SessionLocal() as session:
        assert session.query(Bridge).count() == 1
