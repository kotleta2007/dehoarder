"""GET /api/v1/status: read-only pipeline overview for the web app."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

import dehoarder.db.session as db_session
from dehoarder.db.models import Book, Job, Scan, Tab

router = APIRouter(prefix="/api/v1", tags=["status"])


class StatusOut(BaseModel):
    scans: int
    tabs: int
    books: int
    jobs: int


@router.get("/status", response_model=StatusOut)
def get_status() -> StatusOut:
    with db_session.SessionLocal() as session:
        return StatusOut(
            scans=session.query(Scan).count(),
            tabs=session.query(Tab).count(),
            books=session.query(Book).count(),
            jobs=session.query(Job).count(),
        )
