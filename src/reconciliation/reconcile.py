"""
reconcile.py — dual-path variant reconciliation. This is the core
differentiator per the implementation guide: never cut this.

Pipeline for a single variant:
  1. Annotate via VEP (gene, consequence, gnomAD AF)
  2. Look up AlphaMissense score (missense variants only — indels/nonsense
     aren't scored by AlphaMissense, so this is None for those)
  3. Run the ACMG rule engine (deterministic, "rule path")
  4. Run the ML path:
       - MVP fallback (default, no training needed): use AlphaMissense's own
         am_class directly as the "ML" tier — likely_pathogenic / ambiguous /
         likely_benign
       - Full version (once xgb_classifier.py exists): swap in the trained
         XGBoost prediction instead
  5. Compare rule-path tier vs ML-path tier, flag agreement/disagreement

Usage:
    python -m src.reconciliation.reconcile ENST00000003084:c.1521_1523delCTT
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional

from src.annotation.vep_client import VEPAnnotation, VEPError, annotate_hgvs
from src.scoring.acmg_rules import ACMGInput, ACMGResult, evaluate
from src.scoring.alphamissense import AlphaMissenseScore

try:
    from src.scoring.alphamissense import lookup as am_lookup
except ImportError:  # pragma: no cover
    am_lookup = None


# Three-tier bucket shared by both paths, so they're directly comparable.
# Rule-engine's 5-tier output collapses to this for comparison purposes.
RULE_TIER_TO_BUCKET = {
    "Pathogenic": "pathogenic",
    "Likely Pathogenic": "pathogenic",
    "VUS": "ambiguous",
    "Likely Benign": "benign",
    "Benign": "benign",
}

AM_CLASS_TO_BUCKET = {
    "likely_pathogenic": "pathogenic",
    "ambiguous": "ambiguous",
    "likely_benign": "benign",
}


@dataclass
class ReconciliationResult:
    variant: str
    gene_symbol: Optional[str]
    consequence: Optional[str]
    gnomad_af: Optional[float]

    rule_result: ACMGResult
    rule_bucket: str

    ml_tier: Optional[str]        # raw ML/AlphaMissense label, None if unscoreable
    ml_bucket: Optional[str]
    ml_source: str                 # "alphamissense_native" | "xgboost" | "unavailable"

    agreement: Optional[bool]      # None if ML path had no output to compare

    def explain(self) -> str:
        lines = [
            f"Variant: {self.variant}",
            f"Gene: {self.gene_symbol}  Consequence: {self.consequence}  "
            f"gnomAD AF: {self.gnomad_af}",
            "",
            f"[Rule path]  {self.rule_result.tier}  -> bucket: {self.rule_bucket}",
        ]
        for c in self.rule_result.criteria:
            if c.triggered:
                lines.append(f"    [{c.code}] {c.points:+d} — {c.rationale}")
        lines.append("")
        if self.ml_tier is not None:
            lines.append(
                f"[ML path ({self.ml_source})]  {self.ml_tier}  -> bucket: {self.ml_bucket}"
            )
        else:
            lines.append(f"[ML path ({self.ml_source})]  no score available")
        lines.append("")
        if self.agreement is None:
            lines.append("Agreement: N/A (ML path had no output)")
        else:
            lines.append(f"Agreement: {'YES' if self.agreement else 'NO — FLAGGED FOR REVIEW'}")
        return "\n".join(lines)


def _extract_variant_key(annotation: VEPAnnotation) -> Optional[tuple[str, int, str, str]]:
    """
    Best-effort extraction of (chrom, pos, ref, alt) from a VEP annotation's raw
    response, needed to query the AlphaMissense DuckDB index. VEP's region-based
    calls carry this directly; HGVS-based calls require pulling it out of
    colocated_variants or the 'seq_region_name'/'start'/'allele_string' fields
    when present.
    """
    raw = annotation.raw
    chrom = raw.get("seq_region_name")
    pos = raw.get("start")
    allele_string = raw.get("allele_string")  # e.g. "C/T"
    if chrom and pos and allele_string and "/" in allele_string:
        ref, alt = allele_string.split("/", 1)
        return (f"chr{chrom}", int(pos), ref, alt)
    return None


def _run_ml_path(
    variant_key: Optional[tuple[str, int, str, str]],
) -> tuple[Optional[str], Optional[str], Optional[AlphaMissenseScore], str]:
    """
    MVP ML path: use AlphaMissense's own am_class as the "ML" prediction.
    Returns (ml_tier, ml_bucket, am_score_obj, source_label).
    Swap this out for a real XGBoost call once xgb_classifier.py exists —
    keep the same return shape so reconcile() doesn't need to change.
    """
    if variant_key is None or am_lookup is None:
        return None, None, None, "unavailable"

    try:
        score = am_lookup(*variant_key)
    except FileNotFoundError:
        return None, None, None, "unavailable (no AlphaMissense index built yet)"

    if score is None:
        return None, None, None, "unavailable (not a scored missense variant)"

    bucket = AM_CLASS_TO_BUCKET.get(score.am_class)
    return score.am_class, bucket, score, "alphamissense_native"


def reconcile(hgvs_or_annotation: str | VEPAnnotation) -> ReconciliationResult:
    if isinstance(hgvs_or_annotation, str):
        annotation = annotate_hgvs(hgvs_or_annotation)
        variant_label = hgvs_or_annotation
    else:
        annotation = hgvs_or_annotation
        variant_label = annotation.input_variant

    variant_key = _extract_variant_key(annotation)
    ml_tier, ml_bucket, am_score, ml_source = _run_ml_path(variant_key)

    acmg_input = ACMGInput(
        gene_symbol=annotation.gene_symbol,
        consequence=annotation.most_severe_consequence,
        gnomad_af=annotation.gnomad_af(),
        alphamissense_score=am_score.am_pathogenicity if am_score else None,
    )
    rule_result = evaluate(acmg_input)
    rule_bucket = RULE_TIER_TO_BUCKET[rule_result.tier]

    agreement = None if ml_bucket is None else (rule_bucket == ml_bucket)

    return ReconciliationResult(
        variant=variant_label,
        gene_symbol=annotation.gene_symbol,
        consequence=annotation.most_severe_consequence,
        gnomad_af=annotation.gnomad_af(),
        rule_result=rule_result,
        rule_bucket=rule_bucket,
        ml_tier=ml_tier,
        ml_bucket=ml_bucket,
        ml_source=ml_source,
        agreement=agreement,
    )


if __name__ == "__main__":
    variant = sys.argv[1] if len(sys.argv) > 1 else "ENST00000003084:c.1521_1523delCTT"
    print(f"Reconciling {variant} ...\n")
    try:
        result = reconcile(variant)
        print(result.explain())
    except VEPError as e:
        print(f"FAILED: {e}")
