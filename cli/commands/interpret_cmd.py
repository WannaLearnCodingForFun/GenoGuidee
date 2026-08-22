from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()


def parse_variant_spec(spec: str):
    from app.schemas.variant import CanonicalVariant, GenomeBuild
    build, chrom, pos, alleles = spec.split(":", 3)
    ref, alt = alleles.split(">")
    return CanonicalVariant.from_vcf_fields(GenomeBuild(build), chrom, int(pos), ref, alt)


def print_interpretation(obj) -> None:
    a = obj.acmg_interpretation
    console.print(f"\n[bold cyan]Variant[/bold cyan] {obj.variant.variant_id}"
                  f"  gene=[bold]{obj.annotation.get('gene')}[/bold]"
                  f"  consequence={obj.annotation.get('consequence')}")
    if obj.annotation.get("clinvar"):
        cv = obj.annotation["clinvar"]
        console.print(f"  ClinVar: {cv['clinical_significance']} ({cv['review_status']})")

    if obj.ml_prediction:
        ml = obj.ml_prediction
        probs = " ".join(f"{k}={v:.3f}" for k, v in ml.calibrated_probabilities.items())
        console.print(f"\n[bold]ML PATH[/bold]  model={ml.model_id}")
        console.print(f"  calibrated: {probs}")
        console.print(f"  uncertainty: entropy={ml.uncertainty['entropy']} "
                      f"max_p={ml.uncertainty['max_probability']}  OOD={ml.ood['state']}")
    else:
        console.print("\n[bold]ML PATH[/bold]  [yellow]no trained model registered[/yellow]")

    console.print(f"\n[bold]ACMG PATH[/bold]  ({a.rule_version})")
    t = Table(show_header=True, header_style="dim")
    t.add_column("criterion"); t.add_column("status"); t.add_column("strength"); t.add_column("reason", max_width=70)
    for c in a.criteria:
        if c.status.value == "MET":
            t.add_row(c.id, "[green]MET[/green]", c.applied_strength.value, c.reason)
    for c in a.criteria:
        if c.status.value == "NOT_MET":
            t.add_row(c.id, "[dim]NOT_MET[/dim]", "", c.reason)
    console.print(t)
    ne = a.not_evaluable
    console.print(f"  [dim]NOT_EVALUABLE ({len(ne)}): {', '.join(ne)}[/dim]")

    r = obj.reconciliation
    color = {"CONCORDANT": "green", "DISCORDANT": "red", "ML_UNAVAILABLE": "yellow"}[r.status]
    console.print(f"\n[bold]RECONCILIATION[/bold]  [{color}]{r.status}[/{color}]")
    console.print(f"  final (ACMG authoritative): [bold]{a.classification}[/bold] — {a.combining_rationale}")
    console.print(f"  human review: {'[red]REQUIRED[/red]' if r.human_review_required else 'recommended'}")

    pm = obj.phenotype_match
    if pm.get("phenotype_match_score") is not None:
        console.print(f"  phenotype match: {pm['phenotype_match_score']} (Lin BMA, {pm.get('hpo_version')})")

    if obj.clinical_considerations:
        console.print("\n[bold]CLINICAL CONSIDERATIONS[/bold] (advisory, never prescriptive)")
        for c in obj.clinical_considerations:
            console.print(f"  • [{c.type}] {c.text}")

    if obj.provenance:
        console.print(f"\n[bold]PROVENANCE[/bold]  {obj.provenance.interpretation_id}  tx={obj.provenance.tx_id}")
        console.print(f"  input={obj.provenance.input_hash[:16]}… output={obj.provenance.output_hash[:16]}…")
        console.print(f"  versions: acmg={obj.provenance.acmg_rule_version} "
                      f"annotation={obj.provenance.annotation_version}")


def run(args) -> int:
    from app.services.interpret import InterpretationService
    v = parse_variant_spec(args.variant)
    if args.gene:
        v = v.model_copy(update={"gene": args.gene})
    patient = None
    if args.patient:
        patient = json.loads(Path(args.patient).read_text())
    obj = InterpretationService().interpret(v, patient=patient)
    print_interpretation(obj)
    return 0
