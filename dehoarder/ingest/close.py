"""Close bookkeeping (stage 3). The browser does the closing; this module
decides what may be closed and records what happened.

The web app drives the sequence, one click from the operator:

1. `POST /scans/{id}/archive` → `archive()` writes the archive, then
   `close_list()` returns the archived, still-open tabs (tab id, browser tab
   id, URL). Only this list is ever sent to the extension.
2. The web app re-lists live tabs, keeps only those that still show the
   archived URL, and sends `close_tabs` to the extension.
3. `POST /scans/{id}/closed` → `record_closed()` stores the outcome by tab
   id: `closed_at` for closed tabs, `close_error="missing"` for the rest.

Guards: session-file (SNSS) scans are refused, because their tab ids are
not live browser ids; and `record_closed()` refuses any tab that was not
archived first, so nothing is recorded as closed without an archive line.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

import dehoarder.db.session as db_session
from dehoarder.db.models import Decision, Scan, ScanSource, Tab
from dehoarder.ingest.archive import ScanNotFoundError


class NotClosableError(RuntimeError):
    """The request would close (or record closing) something it must not."""


@dataclass(frozen=True)
class CloseItem:
    tab_id: int
    browser_tab_id: int
    url: str


@dataclass(frozen=True)
class CloseSummary:
    closed: int
    failed: int
    kept: int


def check_closable_scan(session: Session, scan_id: int) -> Scan:
    scan = session.get(Scan, scan_id)
    if scan is None:
        raise ScanNotFoundError(scan_id)
    if scan.source is not ScanSource.extension:
        raise NotClosableError(
            "tabs from a session-file scan cannot be closed; scan with the extension"
        )
    return scan


def close_list(scan_id: int) -> list[CloseItem]:
    """Archived, approved, still-open tabs of an extension scan."""
    with db_session.SessionLocal() as session:
        check_closable_scan(session, scan_id)
        tabs = session.scalars(
            select(Tab)
            .where(
                Tab.scan_id == scan_id,
                Tab.decision == Decision.close,
                Tab.archived_at.is_not(None),
                Tab.closed_at.is_(None),
                Tab.browser_tab_id.is_not(None),
            )
            .order_by(Tab.id)
        )
        return [
            CloseItem(tab_id=t.id, browser_tab_id=t.browser_tab_id, url=t.url)
            for t in tabs
            if t.browser_tab_id is not None
        ]


def summary(session: Session, scan_id: int) -> CloseSummary:
    def count(*where: ColumnElement[bool]) -> int:
        query = select(func.count()).select_from(Tab).where(Tab.scan_id == scan_id, *where)
        return int(session.scalar(query) or 0)

    return CloseSummary(
        closed=count(Tab.closed_at.is_not(None)),
        failed=count(Tab.closed_at.is_(None), Tab.close_error.is_not(None)),
        kept=count(Tab.closed_at.is_(None), Tab.decision != Decision.close),
    )


def record_closed(scan_id: int, closed: list[int], missing: list[int]) -> CloseSummary:
    """Store the extension's result. All-or-nothing: if any tab id is not an
    archived tab of this scan, nothing is written."""
    ids = set(closed) | set(missing)
    if set(closed) & set(missing):
        raise NotClosableError("a tab cannot be both closed and missing")
    with db_session.SessionLocal() as session:
        check_closable_scan(session, scan_id)
        tabs = {
            t.id: t
            for t in session.scalars(select(Tab).where(Tab.scan_id == scan_id, Tab.id.in_(ids)))
        }
        unknown = ids - tabs.keys()
        if unknown:
            raise NotClosableError(f"tabs {sorted(unknown)} are not in scan {scan_id}")
        unarchived = sorted(t.id for t in tabs.values() if t.archived_at is None)
        if unarchived:
            raise NotClosableError(f"tabs {unarchived} were not archived; refusing to record")

        now = datetime.now(UTC)
        for tab_id in closed:
            tab = tabs[tab_id]
            if tab.closed_at is None:
                tab.closed_at = now
            tab.close_error = None
        for tab_id in missing:
            tab = tabs[tab_id]
            if tab.closed_at is None:
                tab.close_error = "missing"
        session.commit()
        return summary(session, scan_id)
