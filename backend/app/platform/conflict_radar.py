"""Evidence conflict radar. Missing ≠ benign. Conflict ≠ confidence."""
from __future__ import annotations

from typing import Any, Optional

PATH_WORDS = ("pathogenic", "likely_pathogenic", "likely pathogenic")
BENIGN_WORDS = ("benign", "likely_benign", "likely benign")


def _side(label: Optional[str]) -> str:
    if not label:
        return "MISSING"
    s = str(label).strip().lower().replace("-", "_").replace(" ", "_")
    if "conflict" in s:
        return "CONFLICTING"
    if s in PATH_WORDS or "pathogenic" in s:
        return "PATHOGENIC_SUPPORT"
    if s in BENIGN_WORDS or s == "benign":
        return "BENIGN_SUPPORT"
    if s in {"vus", "uncertain", "uncertain_significance"}:
        return "UNCERTAIN"
    return "UNCERTAIN"


def _item(name: str, category: str, detail: Any, source: str) -> dict[str, Any]:
    return {"name": name, "category": category, "detail": detail, "source": source}


def aggregate(sources: dict[str, Any]) -> dict[str, Any]:
    """`sources` keys are named evidence channels; absent/None → MISSING."""
    items: list[dict[str, Any]] = []

    def take(name: str, value: Any, source: str, *, treat_false_as_missing: bool = True) -> None:
        if value is None or value == "" or value == "SOURCE_NOT_CONFIGURED":
            items.append(_item(name, "MISSING", value, source))
            return
        if treat_false_as_missing and value is False:
            items.append(_item(name, "MISSING", value, source))
            return
        if isinstance(value, dict) and value.get("availability") in {
            "SOURCE_NOT_CONFIGURED", "NOT_AVAILABLE",
        }:
            items.append(_item(name, "MISSING", value, source))
            return
        if isinstance(value, (int, float)) and name in {"alphamissense", "revel", "cadd", "spliceai"}:
            # Scores are not independent ACMG evidence; record as UNCERTAIN computational.
            items.append(_item(name, "UNCERTAIN", value, source))
            return
        items.append(_item(name, _side(str(value)), value, source))

    take("clinvar", sources.get("clinvar"), "ClinVar")
    take("clingen", sources.get("clingen"), "ClinGen")
    take("gnomad", sources.get("gnomad"), "gnomAD")
    take("alphamissense", sources.get("alphamissense"), "AlphaMissense")
    take("revel", sources.get("revel"), "REVEL")
    take("spliceai", sources.get("spliceai"), "SpliceAI")
    take("cadd", sources.get("cadd"), "CADD")
    take("functional", sources.get("functional"), "functional")
    take("literature", sources.get("literature"), "literature")
    take("acmg", sources.get("acmg"), "ACMG")
    take("ml", sources.get("ml"), "ML")
    take("phenotype", sources.get("phenotype"), "phenotype")

    supporting = [i for i in items if i["category"] == "PATHOGENIC_SUPPORT"]
    contradicting = [i for i in items if i["category"] == "BENIGN_SUPPORT"]
    unknown = [i for i in items if i["category"] in {"UNCERTAIN", "MISSING", "CONFLICTING"}]
    missing = [i for i in items if i["category"] == "MISSING"]
    conflicting_items = [i for i in items if i["category"] == "CONFLICTING"]

    has_p = bool(supporting)
    has_b = bool(contradicting)
    has_dir = has_p or has_b

    if conflicting_items or (has_p and has_b):
        overall = "CONFLICTING"
        confidence = 0.2
    elif not has_dir:
        overall = "INSUFFICIENT"
        confidence = 0.0
    elif missing or unknown:
        overall = "MIXED"
        confidence = 0.45 if (has_p ^ has_b) else 0.3
    else:
        overall = "CONCORDANT"
        confidence = 0.7

    # Explicit: missing never becomes benign; conflict never becomes confidence.
    if overall == "CONFLICTING":
        confidence = min(confidence, 0.25)
    if overall == "INSUFFICIENT":
        confidence = 0.0

    review = overall in {"CONFLICTING", "INSUFFICIENT", "MIXED"}
    ml_side = _side(str(sources.get("ml") or ""))
    acmg_side = _side(str(sources.get("acmg") or ""))
    if sources.get("ml") and sources.get("acmg") and ml_side != acmg_side and "MISSING" not in {ml_side, acmg_side}:
        if ml_side != "UNCERTAIN" and acmg_side != "UNCERTAIN":
            review = True
            overall = "CONFLICTING" if overall == "CONCORDANT" else overall
            confidence = min(confidence, 0.25)

    return {
        "overall_state": overall,
        "supporting_evidence": supporting,
        "contradicting_evidence": contradicting,
        "unknown_evidence": unknown,
        "confidence": round(confidence, 3),
        "human_review_required": review,
        "items": items,
        "note": "Missing evidence is not benign. Conflicting evidence is not confidence. "
                "Computational scores are not independent ACMG evidence.",
    }


def from_interpretation(obj: Any) -> dict[str, Any]:
    ann = obj.annotation or {}
    clinvar = (ann.get("clinvar") or {}).get("clinical_significance")
    pop = obj.population_evidence or {}
    func = obj.functional_evidence or {}
    am = None
    if isinstance(func, dict):
        am = (func.get("alphamissense") or {}).get("am_pathogenicity") if isinstance(func.get("alphamissense"), dict) else func.get("alphamissense")
    ml = obj.ml_prediction.top_class if obj.ml_prediction else None
    acmg = obj.acmg_interpretation.classification if obj.acmg_interpretation else None
    pheno = None
    if obj.phenotype_match and obj.phenotype_match.get("availability") == "AVAILABLE":
        pheno = "uncertain"  # phenotype is context, never pathogenicity
    gd = obj.gene_disease_context or {}
    clingen = None
    if gd.get("clingen_associations"):
        clingen = gd["clingen_associations"][0].get("classification")
    return aggregate({
        "clinvar": clinvar,
        "clingen": clingen,
        "gnomad": None if (isinstance(pop, dict) and pop.get("availability") != "AVAILABLE") else (pop or {}).get("af"),
        "alphamissense": am,
        "revel": None,
        "spliceai": None,
        "cadd": None,
        "functional": None,
        "literature": None,
        "acmg": acmg,
        "ml": ml,
        "phenotype": pheno,
    })
