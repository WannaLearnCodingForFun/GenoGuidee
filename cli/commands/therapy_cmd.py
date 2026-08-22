"""CLI: genoguide therapy — optional somatic oncology ranking proxy."""
from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

PRESETS = [
    ("EGFR", "L858R", "NSCLC"),
    ("BRAF", "V600E", "Melanoma"),
    ("KRAS", "G12C", "NSCLC"),
    ("EGFR", "T790M", "NSCLC"),
]


def _print_result(result) -> None:
    av = result.availability.value if hasattr(result.availability, "value") else result.availability
    color = {
        "AVAILABLE": "green",
        "SOURCE_NOT_CONFIGURED": "yellow",
        "SOURCE_UNAVAILABLE": "red",
        "NOT_APPLICABLE": "dim",
        "SKIPPED": "yellow",
    }.get(av, "white")
    console.print(f"\n[bold]SOMATIC THERAPY[/bold]  [{color}]{av}[/{color}]")
    if result.reason:
        console.print(f"  {result.reason}")
    if result.request:
        console.print(f"  request: {result.request}  hash={ (result.request_hash or '')[:12] }…")
    if result.latency_ms is not None:
        console.print(f"  latency: {result.latency_ms} ms  cached={result.cached}")

    if result.recommendations:
        t = Table(title="Ranked agents (advisory — not a prescription)")
        t.add_column("#", justify="right")
        t.add_column("drug")
        t.add_column("score", justify="right")
        t.add_column("response")
        t.add_column("evidence")
        t.add_column("n")
        for r in result.recommendations:
            ev = r.evidence_level
            ev_s = f"[green]{ev}[/green]" if ev == "A" else ev
            t.add_row(str(r.rank), r.drug, f"{r.score:.3f}", r.response, ev_s,
                      str(r.evidence_count))
        console.print(t)

    console.print(Panel(result.disclaimer, title="disclaimer", border_style="yellow"))


def run(args) -> int:
    from app.services.drug_recommendation import (
        connector_status, normalize_indication, probe_health,
        protein_shorthand, recommend, reset_runtime_state,
    )

    base_url = getattr(args, "url", None) or None
    if getattr(args, "reset_circuit", False):
        reset_runtime_state()

    if args.health:
        console.print(connector_status(base_url=base_url))
        console.print(probe_health(base_url=base_url))
        return 0

    if args.map:
        protein = protein_shorthand(args.map)
        disease = normalize_indication(args.disease) if args.disease else None
        console.print({"protein_shorthand": protein, "indication": disease})
        return 0 if protein else 2

    if args.json_status:
        console.print_json(data=connector_status(base_url=base_url))
        return 0

    gene, variant, disease = args.gene, args.variant, args.disease
    if args.demo:
        gene, variant, disease = PRESETS[0]

    if not (gene and variant and disease):
        console.print("[red]provide --gene --variant --disease, or --demo[/red]")
        console.print("example: genoguide therapy --gene EGFR --variant L858R --disease NSCLC")
        console.print("HGVS.p is accepted: --variant p.Leu858Arg")
        console.print("live host:  --url https://<ngrok-or-lan-host>")
        return 2

    mapped = protein_shorthand(variant) or variant
    result = recommend(gene, mapped, disease, base_url=base_url)
    if args.json:
        console.print_json(data=result.model_dump(mode="json"))
    else:
        _print_result(result)
        if result.availability.value == "SOURCE_NOT_CONFIGURED" and "placeholder" in (result.reason or ""):
            console.print("[yellow]hint:[/yellow] the README host your-host.example is not real. "
                          "Use --url with the live ngrok base (no trailing path).")
    return 0 if result.availability.value in ("AVAILABLE", "SOURCE_NOT_CONFIGURED", "SKIPPED") else 1
