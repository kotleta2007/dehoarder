"""Background job runner.

Runs one pipeline stage function at a time in a background thread and
persists progress to the `job` table so the API (and eventually the web
app) can poll it. Stage functions register themselves under a `JobKind`
value; this module only knows how to run whatever is registered — the real
stage implementations land in later phases.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import dehoarder.db.session as db_session
from dehoarder.db.models import Job, JobKind, JobStatus

_lock = threading.Lock()
_registry: dict[str, StageFn] = {}


class JobAlreadyRunningError(RuntimeError):
    """Raised when a job is requested while another job is still running."""


class UnknownStageError(KeyError):
    """Raised when no stage function is registered for the requested kind."""


@dataclass
class JobContext:
    """Handed to a stage function so it can report progress mid-run."""

    job_id: int

    def report(self, progress: dict) -> None:
        with db_session.SessionLocal() as session:
            job = session.get(Job, self.job_id)
            if job is None:
                raise RuntimeError(f"job {self.job_id} vanished mid-run")
            job.progress = progress
            session.commit()


StageFn = Callable[[JobContext], None]


def register_stage(kind: str, fn: StageFn) -> None:
    _registry[kind] = fn


def clear_registry() -> None:
    _registry.clear()


def is_running() -> bool:
    with db_session.SessionLocal() as session:
        return session.query(Job).filter(Job.status == JobStatus.running).count() > 0


def start_job(kind: str) -> Job:
    if kind not in _registry:
        raise UnknownStageError(kind)

    with _lock:
        if is_running():
            raise JobAlreadyRunningError(kind)

        with db_session.SessionLocal() as session:
            job = Job(kind=JobKind(kind), status=JobStatus.running, started_at=datetime.now(UTC))
            session.add(job)
            session.commit()
            session.refresh(job)
            job_id = job.id

        threading.Thread(target=_run, args=(job_id, _registry[kind]), daemon=True).start()

    with db_session.SessionLocal() as session:
        created = session.get(Job, job_id)
        if created is None:
            raise RuntimeError(f"job {job_id} vanished right after creation")
        return created


def _run(job_id: int, fn: StageFn) -> None:
    ctx = JobContext(job_id=job_id)
    try:
        fn(ctx)
    except Exception as exc:
        with db_session.SessionLocal() as session:
            job = session.get(Job, job_id)
            if job is not None:
                job.status = JobStatus.failed
                job.error = str(exc)
                job.finished_at = datetime.now(UTC)
                session.commit()
        return

    with db_session.SessionLocal() as session:
        job = session.get(Job, job_id)
        if job is not None:
            job.status = JobStatus.done
            job.finished_at = datetime.now(UTC)
            session.commit()
