from __future__ import annotations

from rich.console import Console
from rich.table import Table

from research import acquisition

console = Console()


def run() -> int:
    console.print("[bold cyan]GENOGUIDE RESEARCH ENGINE — STATUS[/bold cyan]\n")

    # Data availability
    table = Table(title="Evidence sources")
    table.add_column("source", style="cyan")
    table.add_column("state")
    manifest = acquisition.load_manifest()
    for name, spec in manifest.items():
        st = acquisition.dataset_status(name, spec)
        state = "[green]AVAILABLE[/green]" if st["present"] else (
            "[yellow]NOT DOWNLOADED[/yellow]" if st["auto_downloadable"] else "[dim]SOURCE_NOT_CONFIGURED[/dim]"
        )
        table.add_row(name, state)
    console.print(table)

    # Engine components
    comp = Table(title="Engine components")
    comp.add_column("component", style="cyan")
    comp.add_column("state")

    def probe(label, fn):
        try:
            detail = fn()
            comp.add_row(label, f"[green]READY[/green] {detail}")
        except Exception as e:  # noqa: BLE001 — status probe must never crash
            comp.add_row(label, f"[red]UNAVAILABLE[/red] [dim]{type(e).__name__}: {e}[/dim]")

    def _acmg():
        from app.interpretation.acmg_v2 import ENGINE_VERSION, CRITERIA_REGISTRY
        return f"v{ENGINE_VERSION}, {len(CRITERIA_REGISTRY)} criteria"

    def _vcf():
        from app.bioinformatics.vcf import bcftools_available
        return "bcftools: " + ("yes" if bcftools_available() else "no (pure-Python fallback)")

    def _phen():
        from app.phenotype.ontology import load_ontology
        onto = load_ontology()
        return f"{len(onto.terms):,} HPO terms"

    def _models():
        import json
        from pathlib import Path
        reg = Path(__file__).resolve().parents[2] / "models" / "registry"
        entries = list(reg.glob("*.json")) if reg.exists() else []
        return f"{len(entries)} registered model(s)"

    def _legacy():
        from app.dataset import ALL_VARIANTS
        return f"legacy demo dataset: {len(ALL_VARIANTS)} variants (SYNTHETIC)"

    probe("ACMG v2 engine", _acmg)
    probe("VCF processing", _vcf)
    probe("Phenotype/HPO", _phen)
    probe("Model registry", _models)
    probe("Legacy demo API", _legacy)
    console.print(comp)
    return 0
