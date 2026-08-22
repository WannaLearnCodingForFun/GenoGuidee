"""
Guaranteed terminal demonstration: three REAL ClinVar variants (BRCA1
frameshift, TP53 missense, CFTR F508del) interpreted live through the full
engine. Nothing precomputed — every run executes evidence assembly, ACMG v2,
ML (if trained), reconciliation, phenotype matching and provenance.
"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from cli.commands.interpret_cmd import print_interpretation

console = Console()

# Real GRCh38 coordinates of well-known variants (verified against the local
# ClinVar 2026-08 release at runtime; if a coordinate is not found in the
# local ClinVar store the demo says so rather than inventing evidence).
DEMO_VARIANTS = [
    ("BRCA1 c.5266dup (p.Gln1756fs) — frameshift", "17", 43057062, "T", "TG",
     {"patient_id": "DEMO-PATIENT-1 (SYNTHETIC)", "hpo_terms": ["HP:0003002", "HP:0000006"]}),
    ("TP53 c.743G>A (p.Arg248Gln) — missense", "17", 7674220, "C", "T",
     {"patient_id": "DEMO-PATIENT-2 (SYNTHETIC)", "hpo_terms": ["HP:0002664"]}),
    ("CFTR c.1521_1523del (p.Phe508del) — inframe deletion", "7", 117559590, "ATCT", "A",
     {"patient_id": "DEMO-PATIENT-3 (SYNTHETIC)", "hpo_terms": ["HP:0006528", "HP:0002613"]}),
]


def run() -> int:
    from app.schemas.variant import CanonicalVariant, GenomeBuild
    from app.services.interpret import InterpretationService

    console.print(Panel.fit(
        "[bold cyan]GENOGUIDE ENGINE[/bold cyan]\n"
        "research-grade interpretation demo — real ClinVar/HPO/constraint data\n"
        "patient contexts are SYNTHETIC and labeled as such",
        border_style="cyan"))

    svc = InterpretationService()
    for title, chrom, pos, ref, alt, patient in DEMO_VARIANTS:
        console.rule(f"[bold]{title}[/bold]")
        v = CanonicalVariant.from_vcf_fields(GenomeBuild.GRCH38, chrom, pos, ref, alt)
        obj = svc.interpret(v, patient=patient)
        print_interpretation(obj)

    from app.provenance2 import ledger
    chain = ledger.verify_chain()
    console.rule()
    console.print(f"ledger chain: {'[green]VALID[/green]' if chain['valid'] else '[red]INVALID[/red]'} "
                  f"({chain['blocks']} blocks)")
    return 0
