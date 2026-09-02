"""Command-line entry point.

Only `serve`, `status`, `db init`, and the non-interactive `run <stage>`
runner exist, per CLAUDE.md. None of them ever prompt.
"""

import enum

import typer
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
    """Start the API + web app and open the browser."""
    typer.echo("serve: not implemented yet (see GAMEPLAN Step 0.4)", err=True)
    raise typer.Exit(code=2)


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
    """Run a single pipeline stage non-interactively. Stub for now."""
    typer.echo(f"run {stage.value}: not implemented yet", err=True)
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
