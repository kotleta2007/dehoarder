"""Close flow, server side: archive returns the close list, /closed records
the outcome, guards refuse session-file scans and unarchived tabs."""

from __future__ import annotations

from fastapi.testclient import TestClient

import dehoarder.db.session as db_session
from dehoarder.db.models import Classification, Decision, Scan, ScanSource, Tab
from dehoarder.ingest.archive import archive_path


def _make_scan(
    decisions: list[Decision], source: ScanSource = ScanSource.extension
) -> tuple[int, list[int]]:
    with db_session.SessionLocal() as session:
        scan = Scan(source=source, tab_count=len(decisions))
        session.add(scan)
        session.flush()
        tabs = [
            Tab(
                scan_id=scan.id,
                browser_tab_id=500 + i,
                window_id=1,
                url=f"https://www.manning.com/books/{i}",
                title=f"Book {i}",
                domain="manning.com",
                classification=Classification.known_shop,
                decision=d,
            )
            for i, d in enumerate(decisions)
        ]
        session.add_all(tabs)
        session.commit()
        return scan.id, [t.id for t in tabs]


def _tab(tab_id: int) -> Tab:
    with db_session.SessionLocal() as session:
        tab = session.get(Tab, tab_id)
        assert tab is not None
        return tab


def test_archive_returns_close_list(client: TestClient) -> None:
    scan_id, ids = _make_scan([Decision.close, Decision.keep, Decision.close])

    body = client.post(f"/api/v1/scans/{scan_id}/archive").json()

    assert body["to_close"] == [
        {"tab_id": ids[0], "browser_tab_id": 500, "url": "https://www.manning.com/books/0"},
        {"tab_id": ids[2], "browser_tab_id": 502, "url": "https://www.manning.com/books/2"},
    ]


def test_record_closed_and_missing(client: TestClient) -> None:
    scan_id, ids = _make_scan([Decision.close, Decision.close, Decision.keep])
    client.post(f"/api/v1/scans/{scan_id}/archive")

    response = client.post(
        f"/api/v1/scans/{scan_id}/closed", json={"closed": [ids[0]], "missing": [ids[1]]}
    )

    assert response.status_code == 200
    assert response.json() == {"closed": 1, "failed": 1, "kept": 1}
    assert _tab(ids[0]).closed_at is not None
    assert _tab(ids[0]).close_error is None
    assert _tab(ids[1]).closed_at is None
    assert _tab(ids[1]).close_error == "missing"

    # the closed tab is no longer offered for closing; the missing one still is
    to_close = client.post(f"/api/v1/scans/{scan_id}/archive").json()["to_close"]
    assert [item["tab_id"] for item in to_close] == [ids[1]]

    [summary] = client.get("/api/v1/scans").json()
    assert (summary["id"], summary["closed"], summary["failed"], summary["kept"]) == (
        scan_id,
        1,
        1,
        1,
    )


def test_unarchived_tab_is_refused_and_nothing_written(client: TestClient) -> None:
    scan_id, ids = _make_scan([Decision.close, Decision.close])
    client.post(f"/api/v1/scans/{scan_id}/archive")
    late_scan, late_ids = _make_scan([Decision.close])  # never archived

    with db_session.SessionLocal() as session:
        tab = session.get(Tab, late_ids[0])
        assert tab is not None
        tab.scan_id = scan_id  # same scan, but not archived
        session.commit()

    response = client.post(
        f"/api/v1/scans/{scan_id}/closed", json={"closed": [ids[0], late_ids[0]], "missing": []}
    )

    assert response.status_code == 409
    assert "not archived" in response.json()["detail"]
    assert _tab(ids[0]).closed_at is None


def test_tab_from_another_scan_is_refused(client: TestClient) -> None:
    scan_id, _ = _make_scan([Decision.close])
    other_scan, other_ids = _make_scan([Decision.close])
    client.post(f"/api/v1/scans/{other_scan}/archive")

    response = client.post(
        f"/api/v1/scans/{scan_id}/closed", json={"closed": other_ids, "missing": []}
    )
    assert response.status_code == 409


def test_closed_and_missing_overlap_is_refused(client: TestClient) -> None:
    scan_id, ids = _make_scan([Decision.close])
    client.post(f"/api/v1/scans/{scan_id}/archive")
    response = client.post(f"/api/v1/scans/{scan_id}/closed", json={"closed": ids, "missing": ids})
    assert response.status_code == 409


def test_session_file_scan_cannot_be_archived_or_closed(client: TestClient) -> None:
    scan_id, ids = _make_scan([Decision.close], source=ScanSource.snss)

    response = client.post(f"/api/v1/scans/{scan_id}/archive")
    assert response.status_code == 409
    assert "session-file" in response.json()["detail"]
    assert not archive_path(scan_id).exists()

    response = client.post(f"/api/v1/scans/{scan_id}/closed", json={"closed": ids, "missing": []})
    assert response.status_code == 409


def test_unknown_scan(client: TestClient) -> None:
    assert client.post("/api/v1/scans/999/archive").status_code == 404
    response = client.post("/api/v1/scans/999/closed", json={"closed": [], "missing": []})
    assert response.status_code == 404


def test_reporting_closed_twice_keeps_first_timestamp(client: TestClient) -> None:
    scan_id, ids = _make_scan([Decision.close])
    client.post(f"/api/v1/scans/{scan_id}/archive")
    client.post(f"/api/v1/scans/{scan_id}/closed", json={"closed": ids, "missing": []})
    first = _tab(ids[0]).closed_at

    client.post(f"/api/v1/scans/{scan_id}/closed", json={"closed": [], "missing": ids})

    tab = _tab(ids[0])
    assert tab.closed_at == first
    assert tab.close_error is None
