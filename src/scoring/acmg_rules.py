"""
acmg_rules.py — deterministic ACMG/AMP rule engine (simplified subset).

Implements the point-based scoring framework from Tavtigian et al. 2018
("Modeling the ACMG/AMP variant classification guidelines as a Bayesian
classification framework") rather than the older qualitative combining rules,
since points sum cleanly and are easy to explain/log.

Point scale (Tavtigian 2018), all evidence expressed as "points" where
Pathogenic Very Strong = +8, Strong = +4, Moderate = +2, Supporting = +1,
and Benign Standalone = -8, Strong = -4, Supporting = -1.

This module implements a *subset* of the 28 ACMG criteria — the ones
computable from VEP + AlphaMissense + gnomAD AF, which is what's actually
available in this pipeline. Criteria NOT implemented (PS1/PS2/PS3/PS4,
PM1/PM3/PM5/PM6, PP1/PP2/PP4/PP5, BP2-BP7, etc.) require family/functional/
segregation data this hackathon build doesn't have — extend later if needed.

Implemented:
  PVS1 (proxy) — predicted loss-of-function consequence in a gene where LOF
                 is a known mechanism of disease (Very Strong, +8)
  PM2  — absent/rare in population databases (Moderate, +2)
  PP3  — computational evidence (AlphaMissense) supports pathogenicity (Supporting, +1)
  BA1  — allele frequency too high to be disease-causing (Standalone benign, -8)
  BS1  — allele frequency higher than expected for the disorder (Strong benign, -4)
  BS2  — observed in healthy adult individuals for a fully penetrant dominant
         disease (Strong benign, -4) — stubbed, needs cohort data not available here
  BP4  — computational evidence suggests no impact (Supporting benign, -1)
  BP7  — silent variant with no predicted splice impact (Supporting benign, -1)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# --- Tunable thresholds (defensible defaults, cite/adjust as needed) ---
RARE_AF_THRESHOLD = 0.0001          # PM2: <0.01% population frequency
BA1_AF_THRESHOLD = 0.05             # BA1: >5% -> too common to be pathogenic
BS1_AF_THRESHOLD = 0.01             # BS1: >1% -> higher than most Mendelian disease prevalence
ALPHAMISSENSE_PATHOGENIC = 0.564    # AlphaMissense's own published "likely pathogenic" cutoff
ALPHAMISSENSE_BENIGN = 0.34         # AlphaMissense's own published "likely benign" cutoff

LOF_CONSEQUENCES = {
    "frameshift_variant",
    "stop_gained",
    "stop_lost",
    "start_lost",
    "splice_acceptor_variant",
    "splice_donor_variant",
    "transcript_ablation",
}

# Hardcode a small set of genes where LOF is an established disease mechanism.
# Extend this list as you add demo variants; this is intentionally minimal.
LOF_MECHANISM_GENES = {"CFTR", "HBB", "GJB2", "HEXA", "BRCA1", "BRCA2"}


class Strength(Enum):
    PATHOGENIC_VERY_STRONG = 8
    PATHOGENIC_STRONG = 4
    PATHOGENIC_MODERATE = 2
    PATHOGENIC_SUPPORTING = 1
    BENIGN_SUPPORTING = -1
    BENIGN_STRONG = -4
    BENIGN_STANDALONE = -8


@dataclass
class CriterionResult:
    code: str
    triggered: bool
    points: int
    rationale: str


@dataclass
class ACMGInput:
    """Everything the rule engine needs, pulled from VEP + AlphaMissense + gnomAD."""
    gene_symbol: str | None
    consequence: str | None          # VEP most_severe_consequence
    gnomad_af: float | None          # population allele frequency, 0-1
    alphamissense_score: float | None  # 0-1, higher = more likely pathogenic
    is_synonymous_no_splice_impact: bool = False  # for BP7; set by caller if known


@dataclass
class ACMGResult:
    total_points: int
    tier: str
    criteria: list[CriterionResult] = field(default_factory=list)

    def explain(self) -> str:
        lines = [f"ACMG tier: {self.tier} (points: {self.total_points:+d})"]
        for c in self.criteria:
            if c.triggered:
                lines.append(f"  [{c.code}] {c.points:+d} — {c.rationale}")
        return "\n".join(lines)


def _tier_from_points(points: int) -> str:
    """
    Points -> tier, per Tavtigian 2018 recommended cutoffs:
      >=10  Pathogenic
      6-9   Likely Pathogenic
      0-5   VUS
      -1 to -6  Likely Benign
      <=-7  Benign
    (BA1 standalone overrides to Benign regardless of other points if triggered alone;
     handled by caller if desired — this function just buckets the sum.)
    """
    if points >= 10:
        return "Pathogenic"
    if 6 <= points <= 9:
        return "Likely Pathogenic"
    if -6 <= points <= 5:
        return "VUS"
    if -9 <= points <= -7:
        return "Likely Benign"
    return "Benign"


def evaluate(variant: ACMGInput) -> ACMGResult:
    criteria: list[CriterionResult] = []

    # PVS1 (proxy) — predicted LOF in a known LOF-mechanism gene
    is_lof = variant.consequence in LOF_CONSEQUENCES
    is_lof_gene = variant.gene_symbol in LOF_MECHANISM_GENES if variant.gene_symbol else False
    pvs1 = is_lof and is_lof_gene
    criteria.append(CriterionResult(
        code="PVS1",
        triggered=pvs1,
        points=Strength.PATHOGENIC_VERY_STRONG.value if pvs1 else 0,
        rationale=(
            f"{variant.consequence} in {variant.gene_symbol}, a gene with an "
            "established loss-of-function disease mechanism"
            if pvs1 else "no LOF consequence in a known LOF-mechanism gene"
        ),
    ))

    # PM2 — absent/rare in population
    af = variant.gnomad_af
    pm2 = af is not None and af < RARE_AF_THRESHOLD
    criteria.append(CriterionResult(
        code="PM2",
        triggered=pm2,
        points=Strength.PATHOGENIC_MODERATE.value if pm2 else 0,
        rationale=(
            f"gnomAD AF {af:.2e} < {RARE_AF_THRESHOLD:.0e} threshold"
            if pm2 else "not rare enough in population data (or AF unknown)"
        ),
    ))

    # PP3 — computational evidence (AlphaMissense) supports pathogenicity
    am = variant.alphamissense_score
    pp3 = am is not None and am >= ALPHAMISSENSE_PATHOGENIC
    criteria.append(CriterionResult(
        code="PP3",
        triggered=pp3,
        points=Strength.PATHOGENIC_SUPPORTING.value if pp3 else 0,
        rationale=(
            f"AlphaMissense score {am:.3f} >= {ALPHAMISSENSE_PATHOGENIC} pathogenic cutoff"
            if pp3 else "AlphaMissense score does not support pathogenicity"
        ),
    ))

    # BA1 — too common to be pathogenic (standalone benign)
    ba1 = af is not None and af > BA1_AF_THRESHOLD
    criteria.append(CriterionResult(
        code="BA1",
        triggered=ba1,
        points=Strength.BENIGN_STANDALONE.value if ba1 else 0,
        rationale=(
            f"gnomAD AF {af:.2e} > {BA1_AF_THRESHOLD:.0%} — too common for a rare Mendelian disease"
            if ba1 else "not common enough to trigger BA1"
        ),
    ))

    # BS1 — higher than expected frequency for the disorder
    bs1 = af is not None and BS1_AF_THRESHOLD < af <= BA1_AF_THRESHOLD
    criteria.append(CriterionResult(
        code="BS1",
        triggered=bs1,
        points=Strength.BENIGN_STRONG.value if bs1 else 0,
        rationale=(
            f"gnomAD AF {af:.2e} above {BS1_AF_THRESHOLD:.0%} expected-prevalence threshold"
            if bs1 else "not triggered"
        ),
    ))

    # BP4 — computational evidence suggests no impact
    bp4 = am is not None and am <= ALPHAMISSENSE_BENIGN
    criteria.append(CriterionResult(
        code="BP4",
        triggered=bp4,
        points=Strength.BENIGN_SUPPORTING.value if bp4 else 0,
        rationale=(
            f"AlphaMissense score {am:.3f} <= {ALPHAMISSENSE_BENIGN} benign cutoff"
            if bp4 else "AlphaMissense score does not support benign"
        ),
    ))

    # BP7 — silent variant, no predicted splice impact
    bp7 = variant.is_synonymous_no_splice_impact
    criteria.append(CriterionResult(
        code="BP7",
        triggered=bp7,
        points=Strength.BENIGN_SUPPORTING.value if bp7 else 0,
        rationale="synonymous with no predicted splice impact" if bp7 else "not triggered",
    ))

    total = sum(c.points for c in criteria if c.triggered)

    # BA1 alone is defined as standalone-sufficient for Benign; enforce that override.
    tier = "Benign" if ba1 else _tier_from_points(total)

    return ACMGResult(total_points=total, tier=tier, criteria=criteria)


if __name__ == "__main__":
    # Quick smoke tests with synthetic inputs (no network needed).
    print("=== Test 1: likely pathogenic CFTR frameshift, rare, high AlphaMissense ===")
    r1 = evaluate(ACMGInput(
        gene_symbol="CFTR",
        consequence="frameshift_variant",
        gnomad_af=0.00001,
        alphamissense_score=0.9,
    ))
    print(r1.explain())

    print("\n=== Test 2: common benign missense ===")
    r2 = evaluate(ACMGInput(
        gene_symbol="CFTR",
        consequence="missense_variant",
        gnomad_af=0.08,
        alphamissense_score=0.1,
    ))
    print(r2.explain())

    print("\n=== Test 3: VUS — rare missense, ambiguous AlphaMissense ===")
    r3 = evaluate(ACMGInput(
        gene_symbol="BRCA1",
        consequence="missense_variant",
        gnomad_af=0.00002,
        alphamissense_score=0.5,
    ))
    print(r3.explain())
