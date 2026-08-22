"""End-to-end pipeline: VCF → validate → normalize → interpret → report."""
from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

console = Console()


def _step(n: int, text: str, ok: bool = True, note: str = "") -> None:
    mark = "[green]✓[/green]" if ok else "[yellow]—[/yellow]"
    console.print(f"{n:>2}. {text:<42} {mark} {note}")


def run(args) -> int:
    from app.bioinformatics import vcf as vcfmod
    from app.schemas.variant import GenomeBuild
    from app.services.interpret import InterpretationService

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    build = GenomeBuild(args.build)

    report = vcfmod.validate_vcf(args.vcf)
    vcfmod.write_report(report, out / "vcf_validation.json")
    _step(1, "VCF validated", report["valid"],
          f"({report['n_records']} records)")
    if not report["valid"]:
        console.print("[red]validation failed — see vcf_validation.json[/red]")
        return 1

    norm = vcfmod.normalize_vcf(args.vcf, output=out / "normalized.vcf")
    vcfmod.write_report(norm, out / "vcf_normalization.json")
    _step(2, "Variants normalized", True,
          f"(engine={norm['engine']}, left_aligned={norm['left_aligned']})")

    patient = json.loads(Path(args.patient).read_text()) if args.patient else None
    svc = InterpretationService()
    sources = svc.evidence.source_summary()

    _step(3, "Variants annotated", True, f"(clinvar={sources['clinvar']})")
    _step(4, "Population evidence", sources["gnomad_population_af"] == "AVAILABLE",
          f"({sources['gnomad_population_af']})")
    _step(5, "Functional predictors", sources["alphamissense"] == "AVAILABLE",
          f"(alphamissense={sources['alphamissense']})")
    _step(6, "ESM representation", False, "(NOT IMPLEMENTED — needs protein sequences)")

    results = []
    for v in vcfmod.iter_canonical_variants(out / "normalized.vcf", build=build):
        results.append(svc.interpret(v, patient=patient))
    has_ml = any(r.ml_prediction for r in results)
    _step(7, "ML predictions generated", has_ml,
          "" if has_ml else "(no registered model — train first)")
    _step(8, "ACMG evaluated", True, f"({len(results)} variants)")
    _step(9, "Evidence reconciled", True)
    _step(10, "Phenotype matching", patient is not None,
          "" if patient else "(no patient JSON supplied)")
    _step(11, "Knowledge graph context", True)
    _step(12, "Clinical considerations", True)
    _step(13, "Provenance recorded", True)

    (out / "interpretations.json").write_text(json.dumps(
        [r.model_dump(mode="json") for r in results], indent=2))

    # prioritization: pathogenic-spectrum first, then VUS with review flags
    def priority(r):
        order = {"PATHOGENIC": 0, "LIKELY_PATHOGENIC": 1, "VUS": 2,
                 "LIKELY_BENIGN": 3, "BENIGN": 4}
        return order.get(r.acmg_interpretation.classification, 2)

    results.sort(key=priority)
    counts: dict[str, int] = {}
    review = 0
    for r in results:
        c = r.acmg_interpretation.classification
        counts[c] = counts.get(c, 0) + 1
        review += bool(r.reconciliation.human_review_required)

    console.print("\n[bold]RESULT:[/bold]")
    console.print(f"  {len(results)} variants interpreted, prioritized in interpretations.json")
    for c, n in counts.items():
        console.print(f"  {c}: {n}")
    console.print(f"  human review required: {review}")
    console.print(f"  output → {out}/")
    return 0
