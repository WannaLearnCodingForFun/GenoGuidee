"""Versioned interpretations + deterministic diffs. Never rewrite history."""
from __future__ import annotations

from typing import Any, Optional

from . import store
from .provenance_upgrade import build_provenance


def _next_version(interpretation_id: str) -> int:
    row = store.execute(
        "SELECT MAX(version) FROM interpretation_versions WHERE interpretation_id=?",
        (interpretation_id,), fetch="one",
    )
    return int(row[0] or 0) + 1 if row else 1


def record(
    *,
    interpretation_id: str,
    classification: str,
    acmg_criteria: Any,
    ml_prediction: Any,
    model_version: Optional[str],
    phenotype_score: Optional[float],
    evidence_ids: list[str],
    kg_version: Optional[str],
    guideline_version: Optional[str],
    timestamp: Optional[float] = None,
    reviewer: Optional[str] = None,
    variant_id: Optional[str] = None,
    case_id: Optional[str] = None,
    patient_id: Optional[int] = None,
    payload: Optional[dict[str, Any]] = None,
    provenance: Optional[dict[str, Any]] = None,
    curation_state: str = "AI_DRAFT",
) -> dict[str, Any]:
    version = _next_version(interpretation_id)
    ts = timestamp if timestamp is not None else store.now()
    store.execute(
        """INSERT INTO interpretation_versions
           (interpretation_id, version, variant_id, case_id, patient_id, classification,
            acmg_criteria_json, ml_prediction_json, model_version, phenotype_score,
            evidence_ids_json, kg_version, guideline_version, reviewer, curation_state,
            payload_json, provenance_json, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (interpretation_id, version, variant_id, case_id, patient_id, classification,
         store.dumps(acmg_criteria), store.dumps(ml_prediction), model_version,
         phenotype_score, store.dumps(evidence_ids), kg_version, guideline_version,
         reviewer, curation_state, store.dumps(payload or {}),
         store.dumps(provenance or {}), ts),
    )
    return get(interpretation_id, version)


def record_from_object(obj: Any) -> Optional[dict[str, Any]]:
    from .evidence_graph import KG_VERSION, attach_interpretation
    from .flags import enabled

    if obj is None or obj.provenance is None:
        return None
    iid = obj.provenance.interpretation_id
    evidence_ids: list[str] = []
    if enabled("ENABLE_EVIDENCE_GRAPH"):
        try:
            evidence_ids = attach_interpretation(obj)
        except Exception:
            evidence_ids = []
    ml = obj.ml_prediction.model_dump(mode="json") if obj.ml_prediction else None
    acmg = obj.acmg_interpretation.model_dump(mode="json") if obj.acmg_interpretation else None
    pheno = None
    if obj.phenotype_match and isinstance(obj.phenotype_match, dict):
        pheno = obj.phenotype_match.get("score") or obj.phenotype_match.get("phenotype_match_score")
    prov = None
    if enabled("ENABLE_PROVENANCE_UPGRADE"):
        prov = build_provenance(obj)
    return record(
        interpretation_id=iid,
        classification=obj.acmg_interpretation.classification if obj.acmg_interpretation else "VUS",
        acmg_criteria=acmg,
        ml_prediction=ml,
        model_version=(obj.ml_prediction.model_version if obj.ml_prediction else None),
        phenotype_score=pheno,
        evidence_ids=evidence_ids,
        kg_version=KG_VERSION,
        guideline_version=obj.acmg_interpretation.rule_version if obj.acmg_interpretation else None,
        timestamp=store.now(),
        variant_id=obj.variant.variant_id if obj.variant else None,
        payload={"reconciliation": obj.reconciliation.model_dump(mode="json") if obj.reconciliation else None,
                 "human_review": obj.human_review},
        provenance=prov,
    )


def _row(r: tuple) -> dict[str, Any]:
    return {
        "id": r[0],
        "interpretation_id": r[1],
        "version": r[2],
        "variant_id": r[3],
        "case_id": r[4],
        "patient_id": r[5],
        "classification": r[6],
        "acmg_criteria": store.loads(r[7], {}),
        "ml_prediction": store.loads(r[8], {}),
        "model_version": r[9],
        "phenotype_score": r[10],
        "evidence_ids": store.loads(r[11], []),
        "kg_version": r[12],
        "guideline_version": r[13],
        "reviewer": r[14],
        "curation_state": r[15],
        "payload": store.loads(r[16], {}),
        "provenance": store.loads(r[17], {}),
        "created_at": r[18],
    }


_COLS = """id, interpretation_id, version, variant_id, case_id, patient_id, classification,
           acmg_criteria_json, ml_prediction_json, model_version, phenotype_score,
           evidence_ids_json, kg_version, guideline_version, reviewer, curation_state,
           payload_json, provenance_json, created_at"""


def get(interpretation_id: str, version: Optional[int] = None) -> Optional[dict[str, Any]]:
    if version is None:
        row = store.execute(
            f"SELECT {_COLS} FROM interpretation_versions WHERE interpretation_id=? ORDER BY version DESC LIMIT 1",
            (interpretation_id,), fetch="one",
        )
    else:
        row = store.execute(
            f"SELECT {_COLS} FROM interpretation_versions WHERE interpretation_id=? AND version=?",
            (interpretation_id, version), fetch="one",
        )
    return _row(row) if row else None


def history(interpretation_id: str) -> list[dict[str, Any]]:
    rows = store.execute(
        f"SELECT {_COLS} FROM interpretation_versions WHERE interpretation_id=? ORDER BY version ASC",
        (interpretation_id,), fetch="all",
    ) or []
    return [_row(r) for r in rows]


def _met(criteria: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(criteria, dict) and "criteria" in criteria:
        criteria = criteria["criteria"]
    if isinstance(criteria, list):
        for c in criteria:
            if not isinstance(c, dict):
                continue
            cid = c.get("id")
            status = c.get("status")
            if cid and str(status).endswith("MET") and "NOT" not in str(status):
                out[cid] = str(c.get("applied_strength") or c.get("default_strength") or "MET")
    return out


def _ml_prob(ml: Any) -> Optional[float]:
    if not isinstance(ml, dict):
        return None
    probs = ml.get("calibrated_probabilities") or ml.get("probabilities") or {}
    top = ml.get("top_class")
    if top and top in probs:
        return float(probs[top])
    if probs:
        return float(max(probs.values()))
    return None


def diff(interpretation_id: str, version_a: int, version_b: int) -> dict[str, Any]:
    a = get(interpretation_id, version_a)
    b = get(interpretation_id, version_b)
    if a is None or b is None:
        raise KeyError("version not found")
    ea, eb = set(a.get("evidence_ids") or []), set(b.get("evidence_ids") or [])
    met_a, met_b = _met(a.get("acmg_criteria")), _met(b.get("acmg_criteria"))
    changed_acmg = []
    for cid in sorted(set(met_a) | set(met_b)):
        if met_a.get(cid) != met_b.get(cid):
            changed_acmg.append({"criterion": cid, "before": met_a.get(cid), "after": met_b.get(cid)})
    pa, pb = _ml_prob(a.get("ml_prediction")), _ml_prob(b.get("ml_prediction"))
    summary_lines = [
        f"{a['classification']} → {b['classification']}" if a["classification"] != b["classification"]
        else f"UNCHANGED: {b['classification']}",
    ]
    for cid in sorted(set(met_b) - set(met_a)):
        summary_lines.append(f"NEW: {cid}_{met_b[cid]}")
    for cid in sorted(set(met_a) - set(met_b)):
        summary_lines.append(f"REMOVED: {cid}")
    if pa is not None and pb is not None and abs(pa - pb) > 1e-6:
        summary_lines.append(f"MODEL: {pa:.2f} → {pb:.2f}")
    if a.get("phenotype_score") != b.get("phenotype_score"):
        summary_lines.append(f"PHENOTYPE: {a.get('phenotype_score')} → {b.get('phenotype_score')}")
    if a.get("reviewer") != b.get("reviewer"):
        summary_lines.append(f"REVIEWER: {a.get('reviewer')} → {b.get('reviewer')}")
    if a["classification"] != b["classification"]:
        summary_lines.append(f"FINAL CHANGE: {a['classification']} → {b['classification']}")
    return {
        "interpretation_id": interpretation_id,
        "version_a": version_a,
        "version_b": version_b,
        "new_evidence": sorted(eb - ea),
        "removed_evidence": sorted(ea - eb),
        "changed_evidence": sorted(ea & eb) if False else [],  # identity-stable ids; strength lives in ACMG
        "changed_acmg_criteria": changed_acmg,
        "changed_model_probability": {"before": pa, "after": pb},
        "changed_phenotype_score": {"before": a.get("phenotype_score"), "after": b.get("phenotype_score")},
        "changed_classification": {"before": a["classification"], "after": b["classification"]},
        "changed_reviewer_decision": {"before": a.get("reviewer"), "after": b.get("reviewer"),
                                      "state_before": a.get("curation_state"),
                                      "state_after": b.get("curation_state")},
        "summary": "\n".join(summary_lines),
        "deterministic": True,
    }
