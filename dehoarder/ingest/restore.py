"""Restore: reopen tabs that the close flow closed (or failed to close).

`restore_list()` returns, for one scan, the archived tabs that are closed
(or, with `only_failed`, those whose close failed), with the URL taken from
the archive file — the record written before anything was closed — and the
database URL only as a fallback. The web app sends those URLs to the
extension (`open_tabs`), then `record_restored()`:

1. appends one `restored` line per tab to `archive/closed-<scan_id>.jsonl`
   (append-only, fsync'ed, before touching the database);
2. clears `closed_at` / `close_error` and sets `decision=keep`, so the next
   "Close approved" does not close the reopened tab again.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

import dehoarder.db.session as db_session
from dehoarder.db.models import Decision, Scan, Tab
from dehoarder.ingest.archive import ScanNotFoundError, append_events, archive_path, read_events


class NotRestorableError(RuntimeError):
    pass


@dataclass(frozen=True)
class RestoreItem:
    tab_id: int
    url: str


def _archived_urls(scan_id: int) -> dict[int, str]:
    return {
        int(e["tab_id"]): str(e["url"])
        for e in read_events(archive_path(scan_id))
        if e.get("event") == "archived" and "tab_id" in e and "url" in e
    }


def restore_list(scan_id: int, only_failed: bool = False) -> list[RestoreItem]:
    with db_session.SessionLocal() as session:
        if session.get(Scan, scan_id) is None:
            raise ScanNotFoundError(scan_id)
        query = select(Tab).where(Tab.scan_id == scan_id, Tab.archived_at.is_not(None))
        if only_failed:
            query = query.where(Tab.closed_at.is_(None), Tab.close_error.is_not(None))
        else:
            query = query.where((Tab.closed_at.is_not(None)) | (Tab.close_error.is_not(None)))
        tabs = list(session.scalars(query.order_by(Tab.id)))

    urls = _archived_urls(scan_id)
    return [RestoreItem(tab_id=t.id, url=urls.get(t.id, t.url)) for t in tabs]


def record_restored(scan_id: int, tab_ids: list[int]) -> int:
    """All-or-nothing: every id must be an archived tab of this scan."""
    with db_session.SessionLocal() as session:
        if session.get(Scan, scan_id) is None:
            raise ScanNotFoundError(scan_id)
        tabs = {
            t.id: t
            for t in session.scalars(
                select(Tab).where(Tab.scan_id == scan_id, Tab.id.in_(set(tab_ids)))
            )
        }
        bad = sorted(set(tab_ids) - {i for i, t in tabs.items() if t.archived_at is not None})
        if bad:
            raise NotRestorableError(f"tabs {bad} are not archived tabs of scan {scan_id}")

        now = datetime.now(UTC)
        urls = _archived_urls(scan_id)
        append_events(
            archive_path(scan_id),
            [
                {
                    "event": "restored",
                    "at": now.isoformat(),
                    "scan_id": scan_id,
                    "tab_id": tab.id,
                    "url": urls.get(tab.id, tab.url),
                }
                for tab in tabs.values()
            ],
        )
        for tab in tabs.values():
            tab.closed_at = None
            tab.close_error = None
            tab.decision = Decision.keep
        session.commit()
        return len(tabs)
