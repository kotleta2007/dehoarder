"""Scans and tabs.

`POST /scans` and `POST /scans/snss` turn a tab list — from the extension or
from a read-only SNSS session file — into a scan + tab rows, then start the
classify job. `GET /tabs` lists a scan's tabs with their classification;
`PATCH /tabs/{id}` and `PATCH /tabs?scan=&shop=|domain=` record the
operator's decisions. Nothing here closes a tab: decisions are only acted on
by the close flow, behind an explicit click.
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

import dehoarder.db.session as db_session
from dehoarder.config import settings
from dehoarder.db.models import Classification, Decision, Scan, ScanSource, Shop, Tab
from dehoarder.ingest.profiles import current_profile, find_profile_by_name
from dehoarder.ingest.snss import read_open_tabs
from dehoarder.jobs.runner import JobAlreadyRunningError, UnknownStageError, start_job

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
    classification: str | None
    shop: str | None
    shop_name: str | None
    closed_at: datetime | None


class ScanOut(BaseModel):
    id: int
    started_at: datetime
    source: str
    profile_name: str | None
    tab_count: int
    tabs: list[TabOut]
    classify_job_id: int | None = None


class DecisionIn(BaseModel):
    decision: Decision


class BulkDecisionOut(BaseModel):
    updated: int


def domain_of(url: str) -> str:
    hostname = urlparse(url).hostname or ""
    return hostname.removeprefix("www.")


def _from_epoch_ms(value: float | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def _shops_by_id(session: Session) -> dict[int, Shop]:
    return {shop.id: shop for shop in session.scalars(select(Shop))}


def _serialize_tab(tab: Tab, shops: dict[int, Shop] | None = None) -> TabOut:
    shop = (shops or {}).get(tab.shop_id) if tab.shop_id is not None else None
    return TabOut(
        id=tab.id,
        url=tab.url,
        title=tab.title,
        domain=tab.domain,
        discarded=tab.discarded,
        decision=tab.decision.value,
        classification=tab.classification.value if tab.classification else None,
        shop=shop.slug if shop else None,
        shop_name=shop.name if shop else None,
        closed_at=tab.closed_at,
    )


def _start_classify() -> int | None:
    """Kick off the classify job for the new scan; None if it cannot start
    now (another job running) — the Tabs view then offers a Classify button."""
    try:
        return start_job("classify").id
    except (UnknownStageError, JobAlreadyRunningError):
        return None


def _check_decision(tab: Tab, decision: Decision) -> None:
    if tab.closed_at is not None:
        raise HTTPException(status_code=409, detail=f"tab {tab.id} is already closed")
    if decision is Decision.close and tab.classification is not Classification.known_shop:
        raise HTTPException(
            status_code=422,
            detail=f"tab {tab.id}: only known-shop tabs can be closed; learn the shop first",
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

        out = ScanOut(
            id=scan.id,
            started_at=scan.started_at,
            source=scan.source.value,
            profile_name=scan.profile_name,
            tab_count=scan.tab_count,
            tabs=[_serialize_tab(t) for t in tabs],
        )

    out.classify_job_id = _start_classify()
    return out


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


@router.get("/tabs", response_model=list[TabOut])
def list_tabs(scan: int, classification: Classification | None = None) -> list[TabOut]:
    with db_session.SessionLocal() as session:
        query = select(Tab).where(Tab.scan_id == scan).order_by(Tab.id)
        if classification is not None:
            query = query.where(Tab.classification == classification)
        shops = _shops_by_id(session)
        return [_serialize_tab(t, shops) for t in session.scalars(query)]


@router.patch("/tabs/{tab_id}", response_model=TabOut)
def set_tab_decision(tab_id: int, payload: DecisionIn) -> TabOut:
    with db_session.SessionLocal() as session:
        tab = session.get(Tab, tab_id)
        if tab is None:
            raise HTTPException(status_code=404, detail="tab not found")
        _check_decision(tab, payload.decision)
        tab.decision = payload.decision
        session.commit()
        return _serialize_tab(tab, _shops_by_id(session))


@router.patch("/tabs", response_model=BulkDecisionOut)
def set_tabs_decision(
    payload: DecisionIn, scan: int, shop: str | None = None, domain: str | None = None
) -> BulkDecisionOut:
    """Set the decision for every open tab of a scan in one shop (by slug)
    or on one domain. Closed tabs are skipped."""
    if (shop is None) == (domain is None):
        raise HTTPException(status_code=422, detail="give exactly one of shop= or domain=")
    with db_session.SessionLocal() as session:
        query = select(Tab).where(Tab.scan_id == scan, Tab.closed_at.is_(None))
        if shop is not None:
            shop_row = session.scalars(select(Shop).where(Shop.slug == shop)).first()
            if shop_row is None:
                raise HTTPException(status_code=404, detail=f"unknown shop {shop!r}")
            query = query.where(Tab.shop_id == shop_row.id)
        else:
            query = query.where(Tab.domain == domain)
        tabs = list(session.scalars(query))
        for tab in tabs:
            _check_decision(tab, payload.decision)
        for tab in tabs:
            tab.decision = payload.decision
        session.commit()
        return BulkDecisionOut(updated=len(tabs))
