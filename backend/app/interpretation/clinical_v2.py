"""
Clinical decision support v2 (sections 39, 75).

Generates clinical CONSIDERATIONS — never prescriptions or diagnoses. Every
consideration carries reason, sources, guideline reference, confidence and a
human-review status.

CLINICAL SAFETY GATE (section 75): considerations beyond "human review
required" are only generated when ACMG has been evaluated AND provenance
metadata is available AND patient context is present AND model confidence is
acceptable (or ML is absent — ACMG-only is permitted with review flags).
"""
from __future__ import annotations

from typing import Any, Optional

from ..schemas.interpretation import (
    AcmgInterpretation, ClinicalConsideration, MlPrediction, Reconciliation)

CDS_VERSION = "cds-v2.0.0"


def safety_gate(acmg: Optional[AcmgInterpretation],
                has_provenance: bool,
                has_patient_context: bool,
                ml: Optional[MlPrediction]) -> tuple[bool, list[str]]:
    reasons = []
    if acmg is None:
        reasons.append("ACMG evidence not evaluated")
    if not has_provenance:
        reasons.append("evidence provenance unavailable")
    if not has_patient_context:
        reasons.append("patient context unavailable")
    if ml is not None:
        if ml.ood and ml.ood.get("state") == "OUT_OF_DISTRIBUTION":
            reasons.append("model input out-of-distribution")
        if ml.uncertainty and ml.uncertainty.get("max_probability", 1.0) < 0.4:
            reasons.append("model confidence unacceptable")
    return (len(reasons) == 0, reasons)


def generate_considerations(
    acmg: AcmgInterpretation,
    reconciliation: Reconciliation,
    phenotype_match: dict[str, Any] | None,
    gene_disease_context: dict[str, Any] | None,
    has_provenance: bool,
    has_patient_context: bool,
    ml: Optional[MlPrediction] = None,
) -> list[ClinicalConsideration]:
    passed, gate_reasons = safety_gate(acmg, has_provenance, has_patient_context, ml)

    def c(type_, text, reason, sources=None, guideline=None, confidence="advisory"):
        return ClinicalConsideration(
            type=type_, text=text, reason=reason, sources=sources or [],
            guideline=guideline, version=CDS_VERSION, confidence=confidence,
            human_review_status="required" if reconciliation.human_review_required else "recommended",
        )

    out: list[ClinicalConsideration] = []

    if not passed:
        out.append(c(
            "human_review", "HUMAN REVIEW REQUIRED before any clinical use.",
            "Clinical safety gate not satisfied: " + "; ".join(gate_reasons),
            confidence="mandatory"))
        return out

    cls = acmg.classification

    if reconciliation.status == "DISCORDANT":
        out.append(c(
            "specialist_review",
            "Discordant ML/ACMG assessment — refer to a clinical molecular geneticist.",
            reconciliation.note, confidence="mandatory"))

    if cls in ("PATHOGENIC", "LIKELY_PATHOGENIC"):
        out.append(c(
            "genetic_counseling",
            "Consider referral for genetic counseling.",
            f"ACMG classification is {cls} ({acmg.combining_rationale}).",
            guideline="ACMG/AMP 2015 (Richards et al., PMID 25741868)"))
        out.append(c(
            "confirmatory_testing",
            "Consider orthogonal confirmatory testing in an accredited laboratory.",
            "Research-pipeline results are not clinically validated.",
            confidence="mandatory"))
        out.append(c(
            "family_testing",
            "Consider cascade/family variant testing where clinically appropriate.",
            "Pathogenic-spectrum germline finding may be heritable.",
            guideline="review applicable clinical guidelines for the associated condition"))
        moi = (gene_disease_context or {}).get("modes_of_inheritance") or []
        if any(m in ("AR", "Autosomal recessive") for m in moi):
            out.append(c(
                "reproductive_counseling",
                "Consider reproductive counseling (autosomal recessive association curated).",
                "ClinGen curates an AR gene-disease relationship for this gene.",
                sources=["ClinGen gene-validity (CC0)"]))

    elif cls == "VUS":
        out.append(c(
            "vus_management",
            "Variant of uncertain significance — do not use for clinical decision-making; "
            "consider periodic reassessment and, where appropriate, family segregation studies.",
            "Evidence currently insufficient for classification.",
            guideline="ACMG/AMP 2015; review applicable clinical guidelines"))

    if phenotype_match and (phenotype_match.get("phenotype_match_score") or 0) >= 0.5:
        out.append(c(
            "phenotype_correlation",
            "Reported patient phenotype shows substantial overlap with this gene's phenotype profile.",
            f"HPO best-match-average similarity "
            f"{phenotype_match['phenotype_match_score']} (Lin, {phenotype_match.get('hpo_version')}).",
            sources=["Human Phenotype Ontology"]))

    out.append(c(
        "scope",
        "Research-grade interpretation — not a diagnosis and not treatment advice.",
        "This engine is a research pipeline, not a validated clinical diagnostic device.",
        confidence="mandatory"))
    return out
