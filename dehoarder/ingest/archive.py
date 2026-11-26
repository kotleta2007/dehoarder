"""Append-only archive of tabs approved for closing.

Before the close flow asks the extension to close anything, `archive()`
writes one JSON line per approved tab to `archive/closed-<scan_id>.jsonl`
and sets `tab.archived_at`. The file is the operator's safety net: every
URL that was ever closed is in it, and restore reads it back.

Rules, all enforced here:

- The file is only ever opened for **append** (`"a"`) or read (`"r"`). It
  is never truncated, rewritten or deleted.
- Lines are flushed and fsync'ed **before** the database marks the tabs
  archived, so a crash can leave an archived line without `archived_at`,
  never the reverse.
- Idempotent: a tab already archived (by `archived_at`, or by an
  `archived` line already in the file after such a crash) is not written
  again.

Restore (stage 3) appends `restored` lines to the same file.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

import dehoarder.db.session as db_session
from dehoarder.config import settings
from dehoarder.db.models import Decision, Scan, Shop, Tab


@dataclass(frozen=True)
class ArchiveResult:
    archived: int  # newly written by this call
    total: int  # tabs of the scan with archived_at set
    path: Path


class ScanNotFoundError(LookupError):
    pass


def archive_path(scan_id: int) -> Path:
    return settings.archive_dir / f"closed-{scan_id}.jsonl"


def read_events(path: Path) -> list[dict[str, Any]]:
    """All lines of an archive file, in order. A torn last line is skipped."""
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def append_events(path: Path, events: list[dict[str, Any]]) -> None:
    """Append JSON lines and fsync. The only way this module writes a file."""
    if not events:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def archive(scan_id: int) -> ArchiveResult:
    """Archive every open `decision=close` tab of the scan not archived yet."""
    path = archive_path(scan_id)
    with db_session.SessionLocal() as session:
        if session.get(Scan, scan_id) is None:
            raise ScanNotFoundError(scan_id)

        tabs = list(
            session.scalars(
                select(Tab)
                .where(
                    Tab.scan_id == scan_id,
                    Tab.decision == Decision.close,
                    Tab.archived_at.is_(None),
                    Tab.closed_at.is_(None),
                )
                .order_by(Tab.id)
            )
        )
        already_in_file = {
            e.get("tab_id") for e in read_events(path) if e.get("event") == "archived"
        }
        shops = {shop.id: shop.slug for shop in session.scalars(select(Shop))}
        now = datetime.now(UTC)

        events = [
            {
                "event": "archived",
                "at": now.isoformat(),
                "scan_id": scan_id,
                "tab_id": tab.id,
                "browser_tab_id": tab.browser_tab_id,
                "window_id": tab.window_id,
                "url": tab.url,
                "title": tab.title,
                "domain": tab.domain,
                "shop": shops.get(tab.shop_id) if tab.shop_id is not None else None,
            }
            for tab in tabs
            if tab.id not in already_in_file
        ]
        append_events(path, events)

        for tab in tabs:
            tab.archived_at = now
        session.commit()

        total = len(
            list(
                session.scalars(
                    select(Tab.id).where(Tab.scan_id == scan_id, Tab.archived_at.is_not(None))
                )
            )
        )
    return ArchiveResult(archived=len(events), total=total, path=path)
