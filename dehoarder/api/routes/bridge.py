"""Bridge routes: the extension's hello handshake and its last-seen status.

One `bridge` row per extension install, keyed by `extension_id`. `hello`
upserts it; `status` reports the most recently seen one, or "not connected"
when none exists yet.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

import dehoarder.db.session as db_session
from dehoarder.db.models import Bridge

router = APIRouter(prefix="/api/v1/bridge", tags=["bridge"])


class HelloIn(BaseModel):
    extension_id: str
    version: str


class BridgeStatusOut(BaseModel):
    connected: bool
    extension_id: str | None = None
    version: str | None = None
    last_seen: datetime | None = None


@router.post("/hello", status_code=204)
def hello(payload: HelloIn) -> None:
    with db_session.SessionLocal() as session:
        bridge = session.get(Bridge, payload.extension_id)
        now = datetime.now(UTC)
        if bridge is None:
            session.add(
                Bridge(extension_id=payload.extension_id, version=payload.version, last_seen=now)
            )
        else:
            bridge.version = payload.version
            bridge.last_seen = now
        session.commit()


@router.get("/status", response_model=BridgeStatusOut)
def status() -> BridgeStatusOut:
    with db_session.SessionLocal() as session:
        bridge = session.query(Bridge).order_by(Bridge.last_seen.desc()).first()
    if bridge is None:
        return BridgeStatusOut(connected=False)
    return BridgeStatusOut(
        connected=True,
        extension_id=bridge.extension_id,
        version=bridge.version,
        last_seen=bridge.last_seen,
    )
