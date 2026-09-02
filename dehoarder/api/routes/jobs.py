"""Job routes: start a stage as a background job, poll its status.

`POST /jobs/{kind}` returns 409 while another job is running (one job at a
time, per CLAUDE.md) and 404 for a stage with no registered implementation.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import dehoarder.db.session as db_session
from dehoarder.db.models import Job
from dehoarder.jobs.runner import JobAlreadyRunningError, UnknownStageError, start_job

router = APIRouter(prefix="/api/v1", tags=["jobs"])


class JobOut(BaseModel):
    id: int
    kind: str
    status: str
    stage: str | None
    progress: dict
    error: str | None


def _serialize(job: Job) -> JobOut:
    return JobOut(
        id=job.id,
        kind=job.kind.value,
        status=job.status.value,
        stage=job.stage,
        progress=job.progress,
        error=job.error,
    )


@router.post("/jobs/{kind}", response_model=JobOut, status_code=201)
def create_job(kind: str) -> JobOut:
    try:
        job = start_job(kind)
    except UnknownStageError:
        raise HTTPException(status_code=404, detail=f"unknown stage {kind!r}") from None
    except JobAlreadyRunningError:
        raise HTTPException(status_code=409, detail="a job is already running") from None
    return _serialize(job)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int) -> JobOut:
    with db_session.SessionLocal() as session:
        job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _serialize(job)


@router.get("/jobs", response_model=list[JobOut])
def list_jobs() -> list[JobOut]:
    with db_session.SessionLocal() as session:
        jobs = session.query(Job).order_by(Job.id.desc()).all()
    return [_serialize(j) for j in jobs]
