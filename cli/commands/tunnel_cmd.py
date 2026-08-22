"""Print / optionally start the ngrok hop in front of the local API."""
from __future__ import annotations

import os
import shutil
import subprocess

from rich.console import Console
from rich.panel import Panel

console = Console()

# Reserved ngrok-free domain for this project. Local uvicorn stays on :8000.
DEFAULT_RESERVED_URL = "https://roxanna-matterless-frightenedly.ngrok-free.dev"


def reserved_url(args) -> str:
    raw = (
        getattr(args, "url", None)
        or os.environ.get("GENOGUIDE_NGROK_URL")
        or DEFAULT_RESERVED_URL
    )
    raw = raw.strip()
    if raw and not raw.startswith("http"):
        raw = "https://" + raw
    return raw.rstrip("/")


def run(args) -> int:
    port = getattr(args, "port", 8000)
    public = reserved_url(args)
    console.print(Panel.fit(
        "[bold cyan]GenoGuide frontend tunnel[/bold cyan]\n"
        f"Local API: 127.0.0.1:{port}  (already running? do not start a second uvicorn)\n"
        f"Public HTTPS: {public}\n"
        "Do not point ngrok at port 80 unless uvicorn is bound there.",
        border_style="cyan"))
    console.print(f"""
[bold]1.[/bold] If [green]curl -s http://127.0.0.1:{port}/api/v1/frontend/health[/green] already
    returns JSON, skip this step. Port {port} in use = the API is up.

    export PYTHONPATH=.
    backend/.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port {port}

[bold]2.[/bold] Authenticate ngrok once (fixes ERR_NGROK_4018):

    ngrok config add-authtoken YOUR_AUTHTOKEN

[bold]3.[/bold] In a [bold]second[/bold] terminal, publish port {port} on the reserved domain
    (not port 80):

    ngrok http {port} --url {public}

[bold]4.[/bold] Frontend [dim]frontend/.env.local[/dim]:

    NEXT_PUBLIC_API_URL={public}
    NEXT_PUBLIC_GENOGUIDE_TUNNEL_KEY=<same as GENOGUIDE_TUNNEL_KEY if you set one>

Frontend calls [bold]POST /api/v1/frontend/therapy[/bold] with
{{mutation, clinical}} and [bold]ngrok-skip-browser-warning[/bold].
No patient identifiers.
""")
    if getattr(args, "start", False):
        ngrok = shutil.which("ngrok")
        if not ngrok:
            console.print("[red]ngrok is not on PATH[/red]")
            return 2
        cmd = [ngrok, "http", str(port), "--url", public]
        console.print(f"[dim]starting:[/dim] {' '.join(cmd)}")
        return subprocess.call(cmd)
    return 0
