"""Command-line entry point.

Only `serve`, `status`, `db init`, and the non-interactive `run <stage>`
runner exist, per CLAUDE.md. None of them ever prompt.
"""

import enum
import threading
import time
import webbrowser

import typer
import uvicorn
from sqlalchemy.exc import OperationalError

from dehoarder.config import settings
from dehoarder.db.migrate import init_db
from dehoarder.db.models import Book, Job, Scan, Tab
from dehoarder.db.session import SessionLocal

app = typer.Typer(add_completion=False, no_args_is_help=True)
db_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(db_app, name="db")


class Stage(enum.StrEnum):
    scan_snss = "scan-snss"
    classify = "classify"
    process = "process"
    tag = "tag"
    link = "link"
    plan = "plan"


@app.command()
def serve(port: int = settings.port, no_open: bool = False) -> None:
    """Start the API + web app, binding 127.0.0.1, and open the browser."""
    from dehoarder.api.app import app as fastapi_app

    url = f"http://127.0.0.1:{port}"

    if not no_open:

        def _open_when_ready() -> None:
            time.sleep(1.0)
            webbrowser.open(url)

        threading.Thread(target=_open_when_ready, daemon=True).start()

    uvicorn.run(fastapi_app, host="127.0.0.1", port=port)


@app.command()
def status() -> None:
    """Read-only overview: counts per stage."""
    try:
        with SessionLocal() as session:
            scan_count = session.query(Scan).count()
            tab_count = session.query(Tab).count()
            book_count = session.query(Book).count()
            job_count = session.query(Job).count()
    except OperationalError:
        typer.echo("database not initialized; run `dehoarder db init` first", err=True)
        raise typer.Exit(code=1) from None

    typer.echo(f"scans:  {scan_count}")
    typer.echo(f"tabs:   {tab_count}")
    typer.echo(f"books:  {book_count}")
    typer.echo(f"jobs:   {job_count}")


@db_app.command("init")
def db_init() -> None:
    """Create the SQLite file and schema."""
    init_db()
    typer.echo(f"initialized {settings.db_path}")


@app.command()
def run(stage: Stage, limit: int | None = typer.Option(None, "--limit")) -> None:
    """Run a single pipeline stage non-interactively."""
    if stage == Stage.scan_snss:
        _run_scan_snss()
        return

    typer.echo(f"run {stage.value}: not implemented yet", err=True)
    raise typer.Exit(code=2)


def _run_scan_snss() -> None:
    from fastapi import HTTPException

    from dehoarder.api.routes.scans import SnssScanIn, create_scan_from_snss

    try:
        scan = create_scan_from_snss(SnssScanIn(profile_name=None))
    except HTTPException as exc:
        typer.echo(str(exc.detail), err=True)
        raise typer.Exit(code=1) from None

    typer.echo(f"profile: {scan.profile_name}")
    typer.echo(f"open tabs: {scan.tab_count}")


if __name__ == "__main__":
    app()
