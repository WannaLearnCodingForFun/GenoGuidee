"""Evidence-grounded explanations. No LLM. No hallucinated citations. No treatment."""
from __future__ import annotations

from typing import Any, Optional


def explain(obj: Any = None, *, acmg: Optional[dict[str, Any]] = None,
            radar: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    claims: list[dict[str, Any]] = []
    unsupported: list[str] = []

    if obj is not None:
        acmg_obj = obj.acmg_interpretation
        acmg = acmg_obj.model_dump(mode="json") if acmg_obj else acmg
        vid = obj.variant.variant_id if obj.variant else None
    else:
        vid = None

    if not acmg:
        return {
            "summary": "INSUFFICIENT EVIDENCE FOR AUTOMATED EXPLANATION",
            "claims": [],
            "unsupported_claims": ["no ACMG record supplied"],
            "confidence": "none",
            "llm_used": False,
            "prescribes_treatment": False,
            "sets_acmg": False,
        }

    classification = acmg.get("classification")
    met = acmg.get("met_criteria") or []
    not_eval = acmg.get("not_evaluable") or []
    claims.append({
        "text": f"Deterministic ACMG/AMP classification is {classification}.",
        "evidence_ids": [f"acmg:{classification}"],
    })
    for c in acmg.get("criteria") or []:
        if str(c.get("status")) in {"MET", "CriterionStatus.MET"} or str(c.get("status", "")).endswith("MET") and "NOT" not in str(c.get("status")):
            eid = f"evidence:{vid or 'variant'}:{c.get('id')}"
            claims.append({
                "text": f"{c.get('id')} is MET ({c.get('applied_strength') or c.get('default_strength')}): {c.get('reason')}",
                "evidence_ids": [eid, *(c.get("sources") or [])],
            })
    if not met:
        claims.append({
            "text": "No ACMG criteria are MET; missing inputs remain NOT_EVALUABLE and are not treated as benign.",
            "evidence_ids": [f"acmg:not_evaluable:{len(not_eval)}"],
        })
    if obj is not None and obj.ml_prediction:
        claims.append({
            "text": (f"Independent ML top class is {obj.ml_prediction.top_class}; "
                     "ML does not override ACMG."),
            "evidence_ids": [f"ml:{obj.ml_prediction.model_id}:{obj.ml_prediction.model_version}"],
        })
    if obj is not None and obj.reconciliation:
        claims.append({
            "text": obj.reconciliation.note,
            "evidence_ids": [f"reconciliation:{obj.reconciliation.status}"],
        })
    if radar and radar.get("overall_state"):
        claims.append({
            "text": f"Evidence radar state is {radar['overall_state']} (confidence {radar.get('confidence')}).",
            "evidence_ids": [f"radar:{radar['overall_state']}"],
        })

    if classification == "VUS" and not met:
        summary = "INSUFFICIENT EVIDENCE FOR AUTOMATED EXPLANATION"
        confidence = "none"
    else:
        summary = claims[0]["text"]
        confidence = acmg.get("confidence") or "low"

    return {
        "summary": summary,
        "claims": claims,
        "unsupported_claims": unsupported,
        "confidence": confidence,
        "llm_used": False,
        "prescribes_treatment": False,
        "sets_acmg": False,
    }
