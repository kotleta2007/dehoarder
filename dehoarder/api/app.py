"""FastAPI application: JSON API under `/api/v1` plus the built web app.

Bound to `127.0.0.1` only — the `serve` CLI command decides host/port when
it calls uvicorn; this module just builds routes.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from dehoarder.api.routes import jobs, status

WEB_DIST = Path(__file__).resolve().parent.parent.parent / "web" / "dist"

app = FastAPI(title="dehoarder")
app.include_router(status.router)
app.include_router(jobs.router)

if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
