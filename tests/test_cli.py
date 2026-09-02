"""CLI tests: `--help`, `status` on an empty DB, and stage/serve stubs.

Runs the CLI as a subprocess so each test gets its own SQLite file via the
`DB_PATH` env var, matching how an operator actually invokes it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run(*args: str, db_path: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["DB_PATH"] = str(db_path)
    return subprocess.run(
        [sys.executable, "-m", "dehoarder.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(db_path.parent),
    )


def test_help(tmp_path: Path) -> None:
    result = _run("--help", db_path=tmp_path / "dehoarder.db")
    assert result.returncode == 0
    assert "status" in result.stdout
    assert "serve" in result.stdout


def test_status_on_empty_db(tmp_path: Path) -> None:
    db_path = tmp_path / "dehoarder.db"
    init_result = _run("db", "init", db_path=db_path)
    assert init_result.returncode == 0
    assert db_path.exists()

    status_result = _run("status", db_path=db_path)
    assert status_result.returncode == 0
    assert "scans:  0" in status_result.stdout
    assert "tabs:   0" in status_result.stdout
    assert "books:  0" in status_result.stdout
    assert "jobs:   0" in status_result.stdout


def test_status_before_db_init(tmp_path: Path) -> None:
    result = _run("status", db_path=tmp_path / "dehoarder.db")
    assert result.returncode == 1
    assert "db init" in result.stderr


def test_run_stage_stub_exits_2(tmp_path: Path) -> None:
    db_path = tmp_path / "dehoarder.db"
    _run("db", "init", db_path=db_path)

    result = _run("run", "classify", db_path=db_path)
    assert result.returncode == 2


def test_run_unknown_stage_is_usage_error(tmp_path: Path) -> None:
    result = _run("run", "not-a-stage", db_path=tmp_path / "dehoarder.db")
    assert result.returncode != 0


def test_serve_stub_exits_2(tmp_path: Path) -> None:
    result = _run("serve", db_path=tmp_path / "dehoarder.db")
    assert result.returncode == 2
