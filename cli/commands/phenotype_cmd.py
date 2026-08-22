from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()


def run(args) -> int:
    from app.phenotype.similarity import rank_diseases, rank_genes

    patient = json.loads(Path(args.patient_json).read_text())
    terms = patient.get("hpo_terms", [])
    if not terms:
        console.print("[red]patient JSON must contain hpo_terms[/red]")
        return 1

    genes = rank_genes(terms, top=args.top)
    t = Table(title=f"Gene ranking (Lin BMA, HPO {genes['hpo_version']})")
    t.add_column("gene", style="cyan"); t.add_column("score"); t.add_column("profile terms")
    for r in genes["ranking"]:
        t.add_row(r["gene"], f"{r['phenotype_match_score']}", str(r.get("n_profile_terms", "")))
    console.print(t)

    diseases = rank_diseases(terms, top=args.top)
    t2 = Table(title="Disease ranking")
    t2.add_column("disease", style="magenta", max_width=55); t2.add_column("id"); t2.add_column("score")
    for r in diseases["ranking"]:
        t2.add_row(r["disease_name"], r["disease_id"], f"{r['phenotype_match_score']}")
    console.print(t2)
    if genes["unknown_terms"]:
        console.print(f"[yellow]unknown HPO terms ignored: {genes['unknown_terms']}[/yellow]")
    return 0
