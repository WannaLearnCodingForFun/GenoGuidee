"""Human curation workflow. No silent modifications. Simulations never become official here."""
from __future__ import annotations

from typing import Any, Optional

from . import store
from .interpretations import get as get_version, record as record_version

STATES = {"AI_DRAFT", "LAB_REVIEW", "CLINICAL_REVIEW", "FINALIZED", "REJECTED", "SUPERSEDED"}

TRANSITIONS = {
    "AI_DRAFT": {"LAB_REVIEW", "CLINICAL_REVIEW", "REJECTED"},
    "LAB_REVIEW": {"CLINICAL_REVIEW", "REJECTED", "AI_DRAFT"},
    "CLINICAL_REVIEW": {"FINALIZED", "REJECTED", "LAB_REVIEW"},
    "REJECTED": {"AI_DRAFT", "SUPERSEDED"},
    "FINALIZED": {"SUPERSEDED"},
    "SUPERSEDED": set(),
}


def _latest(interpretation_id: str) -> dict[str, Any]:
    row = get_version(interpretation_id)
    if row is None:
        raise KeyError("interpretation not found")
    return row


def _event(interpretation_id: str, actor: Optional[str], role: Optional[str], action: str,
           object: Optional[str], before: Any, after: Any, reason: Optional[str],
           request_id: Optional[str]) -> None:
    store.execute(
        """INSERT INTO curation_events
           (interpretation_id, actor, role, action, object, before_json, after_json, reason, request_id, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (interpretation_id, actor, role, action, object, store.dumps(before), store.dumps(after),
         reason, request_id, store.now()),
    )
    store.audit(who=actor, what=action, object=object or interpretation_id,
                before=before, after=after, reason=reason, request_id=request_id)


def transition(interpretation_id: str, new_state: str, *, actor: Optional[str], role: Optional[str],
               reason: str, request_id: Optional[str] = None) -> dict[str, Any]:
    if new_state not in STATES:
        raise ValueError(f"unknown state {new_state}")
    cur = _latest(interpretation_id)
    old = cur["curation_state"]
    allowed = TRANSITIONS.get(old, set())
    if new_state not in allowed:
        raise ValueError(f"cannot transition {old} → {new_state}")
    nxt = record_version(
        interpretation_id=interpretation_id,
        classification=cur["classification"],
        acmg_criteria=cur["acmg_criteria"],
        ml_prediction=cur["ml_prediction"],
        model_version=cur["model_version"],
        phenotype_score=cur["phenotype_score"],
        evidence_ids=cur["evidence_ids"],
        kg_version=cur["kg_version"],
        guideline_version=cur["guideline_version"],
        reviewer=actor,
        variant_id=cur["variant_id"],
        case_id=cur["case_id"],
        patient_id=cur["patient_id"],
        payload=cur["payload"],
        provenance=cur["provenance"],
        curation_state=new_state,
    )
    _event(interpretation_id, actor, role, "transition", "curation_state", old, new_state, reason, request_id)
    return nxt


def mutate_criterion(interpretation_id: str, criterion_id: str, new_status: str, *,
                     actor: Optional[str], role: Optional[str], reason: str,
                     request_id: Optional[str] = None) -> dict[str, Any]:
    cur = _latest(interpretation_id)
    if cur["curation_state"] == "FINALIZED":
        raise ValueError("finalized interpretations are immutable; supersede first")
    criteria = cur["acmg_criteria"]
    before = None
    after = new_status
    if isinstance(criteria, dict) and isinstance(criteria.get("criteria"), list):
        for c in criteria["criteria"]:
            if c.get("id") == criterion_id:
                before = c.get("status")
                c["status"] = new_status
                break
    nxt = record_version(
        interpretation_id=interpretation_id,
        classification=cur["classification"],
        acmg_criteria=criteria,
        ml_prediction=cur["ml_prediction"],
        model_version=cur["model_version"],
        phenotype_score=cur["phenotype_score"],
        evidence_ids=cur["evidence_ids"],
        kg_version=cur["kg_version"],
        guideline_version=cur["guideline_version"],
        reviewer=actor,
        variant_id=cur["variant_id"],
        case_id=cur["case_id"],
        patient_id=cur["patient_id"],
        payload=cur["payload"],
        provenance=cur["provenance"],
        curation_state=cur["curation_state"],
    )
    _event(interpretation_id, actor, role, "change_acmg_evidence", criterion_id, before, after, reason, request_id)
    return nxt


def comment(interpretation_id: str, text: str, *, actor: Optional[str], role: Optional[str],
            request_id: Optional[str] = None) -> dict[str, Any]:
    _event(interpretation_id, actor, role, "comment", "note", None, text, text, request_id)
    return {"ok": True, "interpretation_id": interpretation_id}


def events(interpretation_id: str) -> list[dict[str, Any]]:
    rows = store.execute(
        """SELECT id, actor, role, action, object, before_json, after_json, reason, request_id, created_at
           FROM curation_events WHERE interpretation_id=? ORDER BY id ASC""",
        (interpretation_id,), fetch="all",
    ) or []
    return [{
        "id": r[0], "actor": r[1], "role": r[2], "action": r[3], "object": r[4],
        "before": store.loads(r[5], None), "after": store.loads(r[6], None),
        "reason": r[7], "request_id": r[8], "created_at": r[9],
    } for r in rows]
