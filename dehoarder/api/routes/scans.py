"""POST /api/v1/scans and /api/v1/scans/snss: turn a tab list — from the
extension or from a read-only SNSS session file — into a scan + tab rows.

Read-only bookkeeping — classification, decisions, and closing tabs are
later stages/phases. Domain is derived from the URL so the review UI can
group by shop before anything gets classified.
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import dehoarder.db.session as db_session
from dehoarder.config import settings
from dehoarder.db.models import Scan, ScanSource, Tab
from dehoarder.ingest.profiles import current_profile, find_profile_by_name
from dehoarder.ingest.snss import read_open_tabs

router = APIRouter(prefix="/api/v1", tags=["scans"])


class TabIn(BaseModel):
    windowId: int
    id: int
    url: str
    title: str | None = None
    discarded: bool = False
    lastAccessed: float | None = None


class ScanIn(BaseModel):
    tabs: list[TabIn]


class SnssScanIn(BaseModel):
    profile_name: str | None = None


class TabOut(BaseModel):
    id: int
    url: str
    title: str | None
    domain: str
    discarded: bool
    decision: str


class ScanOut(BaseModel):
    id: int
    started_at: datetime
    source: str
    profile_name: str | None
    tab_count: int
    tabs: list[TabOut]


def domain_of(url: str) -> str:
    hostname = urlparse(url).hostname or ""
    return hostname.removeprefix("www.")


def _from_epoch_ms(value: float | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def _serialize_tab(tab: Tab) -> TabOut:
    return TabOut(
        id=tab.id,
        url=tab.url,
        title=tab.title,
        domain=tab.domain,
        discarded=tab.discarded,
        decision=tab.decision.value,
    )


def _persist_scan(source: ScanSource, profile_name: str | None, raw_tabs: list[dict]) -> ScanOut:
    with db_session.SessionLocal() as session:
        scan = Scan(source=source, profile_name=profile_name, tab_count=len(raw_tabs))
        session.add(scan)
        session.flush()

        tabs = [
            Tab(
                scan_id=scan.id,
                browser_tab_id=t["id"],
                window_id=t["windowId"],
                url=t["url"],
                title=t["title"],
                discarded=t["discarded"],
                last_accessed=_from_epoch_ms(t["lastAccessed"]),
                domain=domain_of(t["url"]),
            )
            for t in raw_tabs
        ]
        session.add_all(tabs)
        session.commit()

        for tab in tabs:
            session.refresh(tab)
        session.refresh(scan)

        return ScanOut(
            id=scan.id,
            started_at=scan.started_at,
            source=scan.source.value,
            profile_name=scan.profile_name,
            tab_count=scan.tab_count,
            tabs=[_serialize_tab(t) for t in tabs],
        )


@router.post("/scans", response_model=ScanOut, status_code=201)
def create_scan(payload: ScanIn) -> ScanOut:
    raw_tabs = [t.model_dump() for t in payload.tabs]
    return _persist_scan(ScanSource.extension, None, raw_tabs)


@router.post("/scans/snss", response_model=ScanOut, status_code=201)
def create_scan_from_snss(payload: SnssScanIn) -> ScanOut:
    if payload.profile_name is not None:
        profile = find_profile_by_name(payload.profile_name)
        if profile is None:
            raise HTTPException(status_code=404, detail=f"unknown profile {payload.profile_name!r}")
    else:
        profile = current_profile()
        if profile is None:
            raise HTTPException(status_code=404, detail="no thorium profile found")

    raw_tabs = read_open_tabs(settings.thorium_dir / profile.dir_name)
    return _persist_scan(ScanSource.snss, profile.display_name, raw_tabs)
