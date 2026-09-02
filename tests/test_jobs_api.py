"""FastAPI + job runner tests: a fake stage that reports progress and
completes, the 409 "one job at a time" conflict, and the status route.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import dehoarder.db.session as db_session
import dehoarder.jobs.runner as runner
from dehoarder.db.migrate import migrate


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path: Path) -> Iterator[None]:
    db_session.configure(str(tmp_path / "test.db"))
    migrate(db_session.engine)
    runner.clear_registry()
    yield
    runner.clear_registry()


@pytest.fixture
def client() -> TestClient:
    from dehoarder.api.app import app

    return TestClient(app)


def test_status_route_on_empty_db(client: TestClient) -> None:
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    assert response.json() == {"scans": 0, "tabs": 0, "books": 0, "jobs": 0}


def test_fake_stage_reports_progress_and_completes(client: TestClient) -> None:
    def fake_stage(ctx: runner.JobContext) -> None:
        ctx.report({"done": 1, "total": 2})
        ctx.report({"done": 2, "total": 2})

    runner.register_stage("scan", fake_stage)

    response = client.post("/api/v1/jobs/scan")
    assert response.status_code == 201
    job_id = response.json()["id"]
    assert response.json()["status"] == "running"

    final = None
    for _ in range(100):
        status_response = client.get(f"/api/v1/jobs/{job_id}")
        final = status_response.json()
        if final["status"] == "done":
            break
        time.sleep(0.02)

    assert final is not None
    assert final["status"] == "done"
    assert final["progress"] == {"done": 2, "total": 2}


def test_failing_stage_is_recorded(client: TestClient) -> None:
    def failing_stage(ctx: runner.JobContext) -> None:
        raise ValueError("boom")

    runner.register_stage("scan", failing_stage)

    job_id = client.post("/api/v1/jobs/scan").json()["id"]

    final = None
    for _ in range(100):
        final = client.get(f"/api/v1/jobs/{job_id}").json()
        if final["status"] == "failed":
            break
        time.sleep(0.02)

    assert final is not None
    assert final["status"] == "failed"
    assert "boom" in final["error"]


def test_unknown_stage_is_404(client: TestClient) -> None:
    response = client.post("/api/v1/jobs/does-not-exist")
    assert response.status_code == 404


def test_second_job_while_running_is_409(client: TestClient) -> None:
    started = threading.Event()
    release = threading.Event()

    def blocking_stage(ctx: runner.JobContext) -> None:
        started.set()
        release.wait(timeout=5)

    runner.register_stage("scan", blocking_stage)

    first = client.post("/api/v1/jobs/scan")
    assert first.status_code == 201
    assert started.wait(timeout=5)

    second = client.post("/api/v1/jobs/scan")
    assert second.status_code == 409

    release.set()


def test_list_jobs(client: TestClient) -> None:
    def fake_stage(ctx: runner.JobContext) -> None:
        pass

    runner.register_stage("scan", fake_stage)
    job_id = client.post("/api/v1/jobs/scan").json()["id"]

    for _ in range(100):
        if client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "done":
            break
        time.sleep(0.02)

    response = client.get("/api/v1/jobs")
    assert response.status_code == 200
    ids = [job["id"] for job in response.json()]
    assert job_id in ids
