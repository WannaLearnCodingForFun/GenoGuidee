from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

console = Console()


def run(command: str, args) -> int:
    from app.bioinformatics import vcf as vcfmod
    from app.schemas.variant import GenomeBuild

    build = GenomeBuild(args.build)

    if command == "validate-vcf":
        report = vcfmod.validate_vcf(args.vcf)
        out = args.output or (args.vcf + ".validation.json")
        vcfmod.write_report(report, out)
        color = "green" if report["valid"] else "red"
        console.print(f"[{color}]{'VALID' if report['valid'] else 'INVALID'}[/{color}] {args.vcf}")
        console.print(f"  records={report['n_records']} samples={report['n_samples']} "
                      f"multiallelic={report['multiallelic_records']} sorted={report['sorted']}")
        for e in report["errors"][:10]:
            console.print(f"  [red]error:[/red] {e}")
        for w in report["warnings"][:5]:
            console.print(f"  [yellow]warn:[/yellow] {w}")
        console.print(f"  report → {out}")
        return 0 if report["valid"] else 1

    if command == "normalize-vcf":
        report = vcfmod.normalize_vcf(args.vcf, output=args.output)
        out = report["output"] + ".normalization.json"
        vcfmod.write_report(report, out)
        console.print(f"[green]normalized[/green] engine={report['engine']} "
                      f"left_aligned={report['left_aligned']}")
        if not report["left_aligned"]:
            console.print(f"  [yellow]{report['left_alignment_note']}[/yellow]")
        console.print(f"  in={report.get('records_in', '?')} out={report.get('records_out', '?')} "
                      f"decomposed={report.get('decomposed', '?')}")
        console.print(f"  output → {report['output']}")
        return 0 if report["success"] else 1

    if command == "annotate":
        from app.services.evidence import EvidenceService
        svc = EvidenceService()
        rows = []
        for v in vcfmod.iter_canonical_variants(args.vcf, build=build):
            ev = svc.annotate(v)
            rows.append(ev)
        out = Path(args.output or (args.vcf + ".annotated.json"))
        out.write_text(json.dumps(rows, indent=2, default=str))
        console.print(f"[green]annotated {len(rows)} variants[/green] → {out}")
        console.print(f"  sources: {svc.source_summary()}")
        return 0

    if command == "interpret-vcf":
        from app.services.interpret import InterpretationService
        svc = InterpretationService()
        results = [
            svc.interpret(v).model_dump(mode="json")
            for v in vcfmod.iter_canonical_variants(args.vcf, build=build)
        ]
        out = Path(args.output or (args.vcf + ".interpretations.json"))
        out.write_text(json.dumps(results, indent=2))
        classes: dict[str, int] = {}
        review = 0
        for r in results:
            c = r["acmg_interpretation"]["classification"]
            classes[c] = classes.get(c, 0) + 1
            review += bool(r["reconciliation"]["human_review_required"])
        console.print(f"[green]interpreted {len(results)} variants[/green] → {out}")
        for c, n in sorted(classes.items()):
            console.print(f"  {c}: {n}")
        console.print(f"  human review required: {review}")
        return 0
    return 2
