"""Registers the real pipeline stage functions with the job runner.

Called once when the API app is built. Tests clear the registry before
each test and call `register_all()` themselves when they need real stages.
"""

from __future__ import annotations

from sqlalchemy import select

import dehoarder.db.session as db_session
from dehoarder.db.models import Scan
from dehoarder.jobs import runner


def latest_scan_id() -> int | None:
    with db_session.SessionLocal() as session:
        return session.scalars(select(Scan.id).order_by(Scan.id.desc()).limit(1)).first()


def _classify_latest(ctx: runner.JobContext) -> None:
    from dehoarder.classify.classify import classify_scan

    scan_id = latest_scan_id()
    if scan_id is None:
        raise RuntimeError("no scan to classify; scan first")
    classify_scan(scan_id, ctx)


def register_all() -> None:
    runner.register_stage("classify", _classify_latest)
