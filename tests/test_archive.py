"""Append-only archive: what gets written, idempotency, never truncating,
and the file modes used."""

from __future__ import annotations

import builtins
import json
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

import dehoarder.db.session as db_session
from dehoarder.db.models import Classification, Decision, Scan, ScanSource, Tab
from dehoarder.ingest import archive as archive_mod
from dehoarder.ingest.archive import ScanNotFoundError, archive, archive_path, read_events


def _make_scan(decisions: list[Decision]) -> tuple[int, list[int]]:
    with db_session.SessionLocal() as session:
        scan = Scan(source=ScanSource.extension, tab_count=len(decisions))
        session.add(scan)
        session.flush()
        tabs = [
            Tab(
                scan_id=scan.id,
                browser_tab_id=100 + i,
                window_id=1,
                url=f"https://www.amazon.de/dp/{i}",
                title=f"Книга {i}",
                domain="amazon.de",
                classification=Classification.known_shop,
                decision=d,
            )
            for i, d in enumerate(decisions)
        ]
        session.add_all(tabs)
        session.commit()
        return scan.id, [t.id for t in tabs]


def _lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_archives_only_approved_tabs() -> None:
    scan_id, ids = _make_scan([Decision.close, Decision.keep, Decision.close, Decision.pending])

    result = archive(scan_id)

    assert (result.archived, result.total) == (2, 2)
    assert result.path == archive_path(scan_id)
    lines = _lines(result.path)
    assert [line["tab_id"] for line in lines] == [ids[0], ids[2]]
    first = lines[0]
    assert first["event"] == "archived"
    assert first["url"] == "https://www.amazon.de/dp/0"
    assert first["title"] == "Книга 0"
    assert first["browser_tab_id"] == 100
    assert first["scan_id"] == scan_id

    with db_session.SessionLocal() as session:
        archived = {t.id for t in session.query(Tab).filter(Tab.archived_at.is_not(None))}
    assert archived == {ids[0], ids[2]}


def test_rerun_appends_nothing() -> None:
    scan_id, _ = _make_scan([Decision.close, Decision.close])
    archive(scan_id)
    before = archive_path(scan_id).read_bytes()

    result = archive(scan_id)

    assert (result.archived, result.total) == (0, 2)
    assert archive_path(scan_id).read_bytes() == before


def test_later_approvals_are_appended_never_truncated() -> None:
    scan_id, ids = _make_scan([Decision.close, Decision.keep])
    path = archive_path(scan_id)
    path.parent.mkdir(parents=True)
    path.write_text('{"event": "note", "from": "an earlier run"}\n', encoding="utf-8")

    archive(scan_id)
    with db_session.SessionLocal() as session:
        tab = session.get(Tab, ids[1])
        assert tab is not None
        tab.decision = Decision.close
        session.commit()
    result = archive(scan_id)

    assert result.archived == 1
    lines = _lines(path)
    assert lines[0] == {"event": "note", "from": "an earlier run"}
    assert [line.get("tab_id") for line in lines[1:]] == [ids[0], ids[1]]


def test_line_in_file_without_db_mark_is_not_duplicated() -> None:
    """Simulates a crash between the fsync and the DB commit."""
    scan_id, ids = _make_scan([Decision.close])
    path = archive_path(scan_id)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"event": "archived", "tab_id": ids[0]}) + "\n", encoding="utf-8")

    result = archive(scan_id)

    assert (result.archived, result.total) == (0, 1)
    assert len(_lines(path)) == 1


def test_only_append_and_read_modes_are_used() -> None:
    scan_id, _ = _make_scan([Decision.close])
    archive(scan_id)  # creates the file, so the second run also reads it
    with db_session.SessionLocal() as session:
        session.add(
            Tab(
                scan_id=scan_id,
                url="https://www.amazon.de/dp/new",
                domain="amazon.de",
                classification=Classification.known_shop,
                decision=Decision.close,
            )
        )
        session.commit()

    with mock.patch.object(archive_mod, "open", wraps=builtins.open, create=True) as mocked:
        archive(scan_id)

    modes = []
    for call in mocked.call_args_list:
        args, kwargs = call
        modes.append(kwargs.get("mode", args[1] if len(args) > 1 else "r"))
    assert sorted(modes) == ["a", "r"]


def test_read_events_skips_a_torn_last_line(tmp_path: Path) -> None:
    path = tmp_path / "x.jsonl"
    path.write_text('{"event": "archived", "tab_id": 1}\n{"event": "arch', encoding="utf-8")
    assert read_events(path) == [{"event": "archived", "tab_id": 1}]


def test_unknown_scan() -> None:
    with pytest.raises(ScanNotFoundError):
        archive(999)


def test_archive_endpoint(client: TestClient) -> None:
    scan_id, _ = _make_scan([Decision.close, Decision.keep])

    response = client.post(f"/api/v1/scans/{scan_id}/archive")
    assert response.status_code == 200
    body = response.json()
    assert (body["archived"], body["total"]) == (1, 1)
    assert body["path"].endswith(f"closed-{scan_id}.jsonl")

    assert client.post(f"/api/v1/scans/{scan_id}/archive").json()["archived"] == 0
    assert client.post("/api/v1/scans/999/archive").status_code == 404
