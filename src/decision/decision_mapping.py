"""
decision_mapping.py — genomic decision mapping.

Two things live here:

1. Evidence-flow trace: shows exactly how a variant's ACMG criteria
   accumulate, step by step, into its final tier. This is the "why did
   the rule engine land here" path — useful for explaining a
   classification to a clinician/judge, not just stating it.

2. Clinical decision tree: maps a reconciled variant classification
   (+ optional carrier-screen / trio-phasing context) to a recommended
   next clinical action. Deterministic, rule-based — no ML here, this
   is meant to be auditable/explainable end to end, same philosophy as
   acmg_rules.py.

Neither of these calls out to VEP/AlphaMissense directly — both take
already-computed results from reconcile.py / carrier_screen.py /
trio_phasing.py as input, so they're cheap to run and easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.family.trio_phasing import PhasedVariant
from src.family.carrier_screen import GeneCarrierFlag
from src.reconciliation.reconcile import ReconciliationResult
from src.scoring.acmg_rules import ACMGResult


# ---------------------------------------------------------------------------
# 1. Evidence-flow trace
# ---------------------------------------------------------------------------

@dataclass
class EvidenceStep:
    order: int
    code: str
    triggered: bool
    points: int
    running_total: int          # cumulative total AFTER this step (only counts triggered criteria)
    rationale: str


@dataclass
class EvidenceTrace:
    steps: list[EvidenceStep]
    final_total: int
    final_tier: str

    def explain(self) -> str:
        lines = [f"Evidence flow -> final tier: {self.final_tier} ({self.final_total:+d} pts)\n"]
        for s in self.steps:
            if s.triggered:
                lines.append(
                    f"  step {s.order}: [{s.code}] {s.points:+d}  "
                    f"(running total: {s.running_total:+d})  — {s.rationale}"
                )
            else:
                lines.append(f"  step {s.order}: [{s.code}] not triggered — {s.rationale}")
        return "\n".join(lines)

    def triggered_only(self) -> list[EvidenceStep]:
        return [s for s in self.steps if s.triggered]


def build_evidence_trace(acmg_result: ACMGResult) -> EvidenceTrace:
    """
    Walk acmg_result.criteria in evaluation order, building a running total
    so you can see exactly which criteria pushed the classification where,
    and by how much, rather than just the final summed tier.
    """
    steps: list[EvidenceStep] = []
    running = 0
    for i, c in enumerate(acmg_result.criteria, start=1):
        if c.triggered:
            running += c.points
        steps.append(EvidenceStep(
            order=i,
            code=c.code,
            triggered=c.triggered,
            points=c.points,
            running_total=running,
            rationale=c.rationale,
        ))
    return EvidenceTrace(steps=steps, final_total=acmg_result.total_points, final_tier=acmg_result.tier)


# ---------------------------------------------------------------------------
# 2. Clinical decision tree
# ---------------------------------------------------------------------------

class ActionPriority(Enum):
    URGENT = "urgent"
    ROUTINE = "routine"
    INFORMATIONAL = "informational"
    NONE = "none"


@dataclass
class ClinicalAction:
    priority: ActionPriority
    recommendation: str
    reasoning: str


@dataclass
class DecisionMapResult:
    variant: str
    tier: str
    agreement: Optional[bool]
    actions: list[ClinicalAction] = field(default_factory=list)

    def explain(self) -> str:
        lines = [f"Decision map for {self.variant} (tier: {self.tier})\n"]
        for a in self.actions:
            lines.append(f"  [{a.priority.value.upper()}] {a.recommendation}")
            lines.append(f"      why: {a.reasoning}")
        return "\n".join(lines)


def map_variant_to_actions(result: ReconciliationResult) -> DecisionMapResult:
    """
    Core decision tree: reconciled tier (+ dual-path agreement) -> recommended
    clinical actions. This does NOT know about family context — see
    map_carrier_flag_to_actions / map_de_novo_to_actions for that, since a
    single variant's tier alone doesn't capture reproductive or inheritance risk.
    """
    tier = result.rule_result.tier
    actions: list[ClinicalAction] = []

    if tier in ("Pathogenic", "Likely Pathogenic"):
        if result.agreement is False:
            actions.append(ClinicalAction(
                priority=ActionPriority.URGENT,
                recommendation="Flag for manual expert review before clinical action",
                reasoning=(
                    f"Rule engine says {tier} but ML path disagrees "
                    f"(ML: {result.ml_tier}) — dual-path disagreement means "
                    "this classification isn't yet reliable enough to act on directly."
                ),
            ))
        else:
            actions.append(ClinicalAction(
                priority=ActionPriority.URGENT,
                recommendation="Refer for genetic counseling; consider orthogonal confirmatory testing",
                reasoning=(
                    f"{tier} classification, rule engine and ML path agree "
                    f"(both -> {result.rule_bucket})."
                ),
            ))
    elif tier == "VUS":
        actions.append(ClinicalAction(
            priority=ActionPriority.INFORMATIONAL,
            recommendation=(
                "No clinical action on this variant alone. Log for periodic "
                "reclassification review; consider functional studies if "
                "phenotype strongly matches the gene."
            ),
            reasoning="Uncertain significance — insufficient evidence either direction.",
        ))
    else:  # Likely Benign / Benign
        actions.append(ClinicalAction(
            priority=ActionPriority.NONE,
            recommendation="No action needed for this variant.",
            reasoning=f"{tier} classification.",
        ))

    return DecisionMapResult(
        variant=result.variant, tier=tier, agreement=result.agreement, actions=actions
    )


def map_carrier_flag_to_actions(flag: GeneCarrierFlag) -> list[ClinicalAction]:
    """Both-partners-carrier result (from carrier_screen.py) -> reproductive counseling action."""
    het_note = " (compound heterozygous)" if flag.compound_het else ""
    return [ClinicalAction(
        priority=ActionPriority.URGENT,
        recommendation=(
            f"Refer couple for reproductive genetic counseling — both partners "
            f"carry a pathogenic {flag.gene} variant{het_note}."
        ),
        reasoning=(
            f"{flag.gene} ({flag.disease}): {flag.recurrence_risk_pct}% recurrence risk "
            "per pregnancy under standard autosomal recessive inheritance."
        ),
    )]


def map_de_novo_to_actions(phased_variant: PhasedVariant) -> list[ClinicalAction]:
    """De novo + pathogenic variant (from trio_phasing.py) -> urgent clinical follow-up."""
    if not phased_variant.high_priority:
        return []
    gene = phased_variant.variant.gene or "this gene"
    return [ClinicalAction(
        priority=ActionPriority.URGENT,
        recommendation=(
            f"Urgent clinical follow-up — de novo pathogenic variant in {gene}, "
            "not present in either parent."
        ),
        reasoning=(
            "De novo pathogenic variants carry clinical significance regardless "
            "of family history, since neither parent's history predicts them."
        ),
    )]


if __name__ == "__main__":
    from src.scoring.acmg_rules import ACMGInput, evaluate

    print("=== Evidence-flow trace demo ===\n")
    acmg_input = ACMGInput(
        gene_symbol="CFTR",
        consequence="frameshift_variant",
        gnomad_af=0.00001,
        alphamissense_score=0.9,
    )
    acmg_result = evaluate(acmg_input)
    trace = build_evidence_trace(acmg_result)
    print(trace.explain())

    print("\n=== Clinical decision tree demo ===\n")
    fake_reconciliation = ReconciliationResult(
        variant="ENST00000003084:c.1521_1523delCTT",
        gene_symbol="CFTR",
        consequence="frameshift_variant",
        gnomad_af=0.00001,
        rule_result=acmg_result,
        rule_bucket="pathogenic",
        ml_tier="likely_pathogenic",
        ml_bucket="pathogenic",
        ml_source="alphamissense_native",
        agreement=True,
    )
    decision = map_variant_to_actions(fake_reconciliation)
    print(decision.explain())

    print("\n=== Disagreement case ===\n")
    fake_disagreement = ReconciliationResult(
        variant="chr1:12345 A>T",
        gene_symbol="TEST",
        consequence="missense_variant",
        gnomad_af=0.00002,
        rule_result=acmg_result,
        rule_bucket="pathogenic",
        ml_tier="likely_benign",
        ml_bucket="benign",
        ml_source="alphamissense_native",
        agreement=False,
    )
    decision2 = map_variant_to_actions(fake_disagreement)
    print(decision2.explain())
