"""
TriageOps CLI — `triageops` command.

Usage:
    triageops                    # read from stdin
    triageops error.log          # read from a file
    triageops error.log --json   # output raw JSON
    triageops --version          # print version

Examples:
    kubectl describe pod web-7d9 | triageops
    docker logs api --tail 200 2>&1 | triageops
    journalctl -u nginx -n 100 --no-pager | triageops --json
    triageops build.log
"""

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from . import __version__
from .pipeline import run_triage
from .render import to_json, to_markdown

app = typer.Typer(
    name="triageops",
    help="DevOps incident triage agent — classify, diagnose, and report infrastructure failures.",
    no_args_is_help=False,
    add_completion=True,
)

console = Console()
error_console = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"TriageOps v{__version__}")
        raise typer.Exit()


@app.command()
def main(
    file: Path | None = typer.Argument(
        default=None,
        help="Path to a log file. Reads from stdin if not provided.",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Output raw JSON instead of formatted markdown.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress the TriageOps header banner.",
    ),
    version: bool | None = typer.Option(
        None,
        "--version",
        "-v",
        callback=_version_callback,
        is_eager=True,
        help="Print version and exit.",
    ),
) -> None:
    """
    Analyse a server, Docker, or Kubernetes problem from a log file or stdin.

    TriageOps will classify the issue, identify the root cause with evidence,
    suggest safe fix commands, and produce a confidence-rated incident report.
    """
    # ------------------------------------------------------------------
    # Read input
    # ------------------------------------------------------------------
    if file:
        if not file.exists():
            error_console.print(f"[red]Error:[/red] File not found: {file}")
            raise typer.Exit(code=1)
        raw_input = file.read_text(encoding="utf-8", errors="replace")
    elif not sys.stdin.isatty():
        raw_input = sys.stdin.read()
    else:
        # Interactive: prompt the user
        if not quiet:
            console.print(
                Panel(
                    "[bold cyan]TriageOps[/bold cyan] — DevOps Incident Triage Agent\n"
                    "[dim]Paste your error message or log, then press Ctrl+D (EOF).[/dim]",
                    border_style="cyan",
                )
            )
        lines = []
        try:
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            pass
        raw_input = "\n".join(lines)

    # ------------------------------------------------------------------
    # Banner
    # ------------------------------------------------------------------
    if not quiet and not json_out:
        console.print()
        console.print(
            Panel(
                Text.assemble(
                    ("TriageOps ", "bold cyan"),
                    (f"v{__version__}", "dim"),
                    (" — Analysing incident...", "white"),
                ),
                border_style="cyan",
                padding=(0, 2),
            )
        )
        console.print()

    # ------------------------------------------------------------------
    # Run pipeline
    # ------------------------------------------------------------------
    try:
        with console.status("[cyan]Running triage pipeline...[/cyan]", spinner="dots"):
            report = run_triage(raw_input)
    except Exception as exc:
        error_console.print(f"[red]Pipeline error:[/red] {exc}")
        raise typer.Exit(code=2)

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    if json_out:
        console.print(to_json(report))
    else:
        md = to_markdown(report)
        console.print(Markdown(md))


@app.command("serve")
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host address to bind."),
    port: int = typer.Option(8000, "--port", "-p", help="Port to listen on."),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload for development."),
) -> None:
    """Launch the TriageOps REST API and Command Center Web UI."""
    import uvicorn

    display_host = "localhost" if host == "0.0.0.0" else host
    console.print(
        Panel(
            f"[bold cyan]TriageOps[/bold cyan] Web Command Center\n"
            f"[dim]Frontend & API running at:[/dim] [bold green]http://{display_host}:{port}[/bold green]\n"
            f"[dim]Swagger Docs at:[/dim] [bold blue]http://{display_host}:{port}/docs[/bold blue]",
            border_style="cyan",
        )
    )
    uvicorn.run("triageops.api:app", host=host, port=port, reload=reload)


@app.command("ui")
def ui(
    port: int = typer.Option(8501, "--port", "-p", help="Port to listen on."),
) -> None:
    """Launch the TriageOps Streamlit UI."""
    import subprocess

    app_path = Path(__file__).parent / "ui" / "app.py"
    console.print(
        Panel(
            f"[bold cyan]TriageOps[/bold cyan] Streamlit UI\n"
            f"[dim]Running at:[/dim] [bold green]http://localhost:{port}[/bold green]",
            border_style="cyan",
        )
    )
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port)])


if __name__ == "__main__":
    app()
