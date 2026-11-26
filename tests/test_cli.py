"""CLI tests: `--help`, `status` on an empty DB, and the `run` stage stub.

Runs the CLI as a subprocess so each test gets its own SQLite file via the
`DB_PATH` env var, matching how an operator actually invokes it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run(
    *args: str, db_path: Path, thorium_dir: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["DB_PATH"] = str(db_path)
    env["OPENROUTER_API_KEY"] = ""  # never reach the network from a test
    if thorium_dir is not None:
        env["THORIUM_DIR"] = str(thorium_dir)
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

    result = _run("run", "process", db_path=db_path)
    assert result.returncode == 2


def test_run_classify_without_scan_exits_1(tmp_path: Path) -> None:
    db_path = tmp_path / "dehoarder.db"
    _run("db", "init", db_path=db_path)

    result = _run("run", "classify", db_path=db_path)
    assert result.returncode == 1
    assert "scan first" in result.stderr


def test_run_unknown_stage_is_usage_error(tmp_path: Path) -> None:
    result = _run("run", "not-a-stage", db_path=tmp_path / "dehoarder.db")
    assert result.returncode != 0


def test_serve_help_lists_port_and_no_open(tmp_path: Path) -> None:
    result = _run("serve", "--help", db_path=tmp_path / "dehoarder.db")
    assert result.returncode == 0
    assert "--port" in result.stdout
    assert "--no-open" in result.stdout


FIXTURE_THORIUM_DIR = Path(__file__).parent / "fixtures" / "thorium_with_session"


def test_run_scan_snss(tmp_path: Path) -> None:
    db_path = tmp_path / "dehoarder.db"
    _run("db", "init", db_path=db_path)

    result = _run("run", "scan-snss", db_path=db_path, thorium_dir=FIXTURE_THORIUM_DIR)
    assert result.returncode == 0
    assert "profile: Test Profile" in result.stdout
    assert "open tabs: 2" in result.stdout


def test_run_classify_after_scan(tmp_path: Path) -> None:
    db_path = tmp_path / "dehoarder.db"
    _run("db", "init", db_path=db_path)
    _run("run", "scan-snss", db_path=db_path, thorium_dir=FIXTURE_THORIUM_DIR)

    result = _run("run", "classify", db_path=db_path)
    assert result.returncode == 0, result.stderr
    counts = dict(line.split(": ") for line in result.stdout.splitlines() if line.count(": ") == 1)
    assert sum(int(counts[k]) for k in ("known_shop", "unknown_book", "not_book")) == 2


def test_run_scan_snss_with_no_profile_exits_1(tmp_path: Path) -> None:
    db_path = tmp_path / "dehoarder.db"
    _run("db", "init", db_path=db_path)

    result = _run(
        "run", "scan-snss", db_path=db_path, thorium_dir=tmp_path / "no-such-thorium-dir"
    )
    assert result.returncode == 1
    assert "no thorium profile found" in result.stderr
