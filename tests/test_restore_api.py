"""Restore, server side: restore list (all / only failed), URLs from the
archive file, restored lines appended, DB state reset."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

import dehoarder.db.session as db_session
from dehoarder.db.models import Classification, Decision, Scan, ScanSource, Tab
from dehoarder.ingest.archive import archive_path


def _closed_scan(client: TestClient) -> tuple[int, list[int]]:
    """Scan with four tabs: closed, failed, kept, closed."""
    decisions = [Decision.close, Decision.close, Decision.keep, Decision.close]
    with db_session.SessionLocal() as session:
        scan = Scan(source=ScanSource.extension, tab_count=len(decisions))
        session.add(scan)
        session.flush()
        tabs = [
            Tab(
                scan_id=scan.id,
                browser_tab_id=700 + i,
                url=f"https://bookvoed.ru/product/{i}",
                title=f"Книга {i}",
                domain="bookvoed.ru",
                classification=Classification.known_shop,
                decision=d,
            )
            for i, d in enumerate(decisions)
        ]
        session.add_all(tabs)
        session.commit()
        scan_id, ids = scan.id, [t.id for t in tabs]

    client.post(f"/api/v1/scans/{scan_id}/archive")
    client.post(
        f"/api/v1/scans/{scan_id}/closed", json={"closed": [ids[0], ids[3]], "missing": [ids[1]]}
    )
    return scan_id, ids


def _tab(tab_id: int) -> Tab:
    with db_session.SessionLocal() as session:
        tab = session.get(Tab, tab_id)
        assert tab is not None
        return tab


def test_restore_list_all_and_only_failed(client: TestClient) -> None:
    scan_id, ids = _closed_scan(client)

    everything = client.get(f"/api/v1/scans/{scan_id}/restore-list").json()
    assert [i["tab_id"] for i in everything] == [ids[0], ids[1], ids[3]]
    assert everything[0]["url"] == "https://bookvoed.ru/product/0"

    failed = client.get(f"/api/v1/scans/{scan_id}/restore-list?only_failed=true").json()
    assert [i["tab_id"] for i in failed] == [ids[1]]


def test_restore_list_prefers_the_archived_url(client: TestClient) -> None:
    scan_id, ids = _closed_scan(client)
    with db_session.SessionLocal() as session:
        tab = session.get(Tab, ids[0])
        assert tab is not None
        tab.url = "https://changed.example/"
        session.commit()

    items = client.get(f"/api/v1/scans/{scan_id}/restore-list").json()
    assert items[0]["url"] == "https://bookvoed.ru/product/0"


def test_restored_appends_lines_and_resets_tabs(client: TestClient) -> None:
    scan_id, ids = _closed_scan(client)
    path = archive_path(scan_id)
    before = path.read_text(encoding="utf-8")

    response = client.post(f"/api/v1/scans/{scan_id}/restored", json={"tab_ids": [ids[0], ids[1]]})

    assert response.json() == {"restored": 2}
    after = path.read_text(encoding="utf-8")
    assert after.startswith(before)
    new_lines = [json.loads(line) for line in after[len(before) :].splitlines()]
    assert {(e["event"], e["tab_id"]) for e in new_lines} == {
        ("restored", ids[0]),
        ("restored", ids[1]),
    }

    for tab_id in (ids[0], ids[1]):
        tab = _tab(tab_id)
        assert (tab.closed_at, tab.close_error, tab.decision) == (None, None, Decision.keep)
        assert tab.archived_at is not None
    assert _tab(ids[3]).closed_at is not None

    # restored tabs are no longer offered for closing or restoring
    assert client.post(f"/api/v1/scans/{scan_id}/archive").json()["to_close"] == []
    items = client.get(f"/api/v1/scans/{scan_id}/restore-list").json()
    assert [i["tab_id"] for i in items] == [ids[3]]


def test_restored_refuses_unarchived_tab_and_writes_nothing(client: TestClient) -> None:
    scan_id, ids = _closed_scan(client)
    before = archive_path(scan_id).read_text(encoding="utf-8")

    response = client.post(f"/api/v1/scans/{scan_id}/restored", json={"tab_ids": [ids[0], ids[2]]})

    assert response.status_code == 409
    assert archive_path(scan_id).read_text(encoding="utf-8") == before
    assert _tab(ids[0]).closed_at is not None


def test_unknown_scan(client: TestClient) -> None:
    assert client.get("/api/v1/scans/999/restore-list").status_code == 404
    assert client.post("/api/v1/scans/999/restored", json={"tab_ids": []}).status_code == 404
