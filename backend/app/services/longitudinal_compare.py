"""Compare genomic snapshots. Disappearance is 'not detected', not clearance."""
from __future__ import annotations

from typing import Any, Optional

from .risk_forecast import linear_slope
from .trajectory_score import classification_severity, variant_trajectory_score
from .variant_normalize import canonical_id_from_record

NOT_DETECTED = "Not detected in current sample"


def _by_canonical(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("detected") is False:
            continue
        try:
            key = canonical_id_from_record(row)
        except ValueError:
            continue
        out[key] = {**row, "canonical_variant_id": key}
    return out


def _pct_delta(prev: Optional[float], cur: Optional[float]) -> Optional[float]:
    if prev is None or cur is None:
        return None
    if prev == 0:
        return None
    return round((cur - prev) / abs(prev) * 100.0, 3)


def compare_snapshots(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]] | None,
    *,
    current_risk: float | None = None,
    previous_risk: float | None = None,
) -> dict[str, Any]:
    cur = _by_canonical(current)
    prev = _by_canonical(previous or [])
    new_ids = sorted(set(cur) - set(prev)) if prev else sorted(cur)
    gone_ids = sorted(set(prev) - set(cur)) if prev else []
    persist_ids = sorted(set(cur) & set(prev)) if prev else []

    reclassified = []
    vaf_changes = []
    ml_changes = []
    evidence_changes = []
    for key in persist_ids:
        a, b = prev[key], cur[key]
        prev_cls = a.get("acmg_classification")
        cur_cls = b.get("acmg_classification")
        if prev_cls and cur_cls and prev_cls != cur_cls:
            reclassified.append({
                "canonical_variant_id": key,
                "gene": b.get("gene"),
                "from": prev_cls,
                "to": cur_cls,
            })
        pv, cv = a.get("allele_frequency"), b.get("allele_frequency")
        if pv is not None and cv is not None:
            vaf_changes.append({
                "canonical_variant_id": key,
                "gene": b.get("gene"),
                "previous": pv,
                "current": cv,
                "delta": round(cv - pv, 6),
                "percent_delta": _pct_delta(pv, cv),
            })
        pp, cp = a.get("pathogenicity_probability"), b.get("pathogenicity_probability")
        if pp is not None and cp is not None:
            ml_changes.append({
                "canonical_variant_id": key,
                "gene": b.get("gene"),
                "previous": pp,
                "current": cp,
                "delta": round(cp - pp, 6),
            })
        prev_crit = set(a.get("acmg_criteria") or [])
        cur_crit = set(b.get("acmg_criteria") or [])
        if prev_crit or cur_crit:
            added = sorted(cur_crit - prev_crit)
            removed = sorted(prev_crit - cur_crit)
            if added or removed or prev_cls != cur_cls:
                evidence_changes.append({
                    "canonical_variant_id": key,
                    "criteria_added": added,
                    "criteria_removed": removed,
                    "classification_changed": prev_cls != cur_cls,
                })

    risk_delta = None
    if current_risk is not None and previous_risk is not None:
        risk_delta = {
            "previous": previous_risk,
            "current": current_risk,
            "delta": round(current_risk - previous_risk, 2),
            "percent_change": _pct_delta(previous_risk, current_risk),
        }

    return {
        "newly_detected": [_card(cur[k]) for k in new_ids],
        "persistent": [_card(cur[k]) for k in persist_ids],
        "not_detected_in_current_sample": [
            {**_card(prev[k]), "label": NOT_DETECTED, "biological_clearance": False}
            for k in gone_ids
        ],
        "reclassified": reclassified,
        "vaf_changes": vaf_changes,
        "ml_probability_changes": ml_changes,
        "acmg_evidence_changes": evidence_changes,
        "risk_change": risk_delta,
        "counts": {
            "newly_detected": len(new_ids),
            "persistent": len(persist_ids),
            "not_detected_in_current_sample": len(gone_ids),
            "reclassified": len(reclassified),
        },
        "not_detected_note": (
            "Absence in the current sample may reflect detection limit, sampling, "
            "sequencing differences, technical variation, or coverage. It is not "
            "interpreted as biological elimination."
        ),
    }


def _card(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_variant_id": row.get("canonical_variant_id"),
        "gene": row.get("gene"),
        "hgvs": row.get("hgvs") or row.get("hgvs_c"),
        "acmg_classification": row.get("acmg_classification"),
        "allele_frequency": row.get("allele_frequency"),
        "pathogenicity_probability": row.get("pathogenicity_probability"),
    }


def variant_history(points: list[dict[str, Any]]) -> dict[str, Any]:
    detected = [p for p in points if p.get("detected") is not False]
    vafs = [float(p["allele_frequency"]) for p in detected if p.get("allele_frequency") is not None]
    probs = [
        float(p["pathogenicity_probability"])
        for p in detected if p.get("pathogenicity_probability") is not None
    ]
    scores = [
        float(p["trajectory_score"])
        for p in detected if p.get("trajectory_score") is not None
    ]
    n_tests = len({p.get("snapshot_id") for p in points if p.get("snapshot_id") is not None}) or len(points)
    n_det = len({p.get("snapshot_id") for p in detected if p.get("snapshot_id") is not None}) or len(detected)
    vaf_slope = linear_slope(vafs)
    p_slope = linear_slope(probs)
    risk_slope = linear_slope(scores)
    if len(vafs) < 2 and len(probs) < 2:
        trend = "INSUFFICIENT_DATA"
    else:
        slope = vaf_slope if vaf_slope is not None else p_slope or 0.0
        if abs(slope) < 0.01:
            trend = "STABLE"
        else:
            trend = "INCREASING" if slope > 0 else "DECREASING"
    latest = detected[-1] if detected else (points[-1] if points else {})
    scored = variant_trajectory_score(
        pathogenicity_probability=latest.get("pathogenicity_probability"),
        acmg_classification=latest.get("acmg_classification"),
        vaf=latest.get("allele_frequency"),
        vaf_slope=vaf_slope,
        detection_rate=(n_det / n_tests) if n_tests else None,
        confidence=latest.get("confidence"),
    )
    return {
        "canonical_variant_id": latest.get("canonical_variant_id"),
        "gene": latest.get("gene"),
        "hgvs": latest.get("hgvs") or latest.get("hgvs_c"),
        "first_detected": detected[0].get("test_date") if detected else None,
        "last_detected": detected[-1].get("test_date") if detected else None,
        "number_of_tests_detected": n_det,
        "detection_rate": round(n_det / n_tests, 4) if n_tests else 0,
        "vaf_min": min(vafs) if vafs else None,
        "vaf_max": max(vafs) if vafs else None,
        "vaf_mean": round(sum(vafs) / len(vafs), 6) if vafs else None,
        "vaf_slope": vaf_slope,
        "pathogenicity_probability_slope": p_slope,
        "risk_score_slope": risk_slope,
        "classification_history": [p.get("acmg_classification") for p in points],
        "points": points,
        "trend": trend,
        "current_classification": latest.get("acmg_classification"),
        "current_vaf": latest.get("allele_frequency"),
        "current_pathogenicity_probability": latest.get("pathogenicity_probability"),
        **scored,
        "severity": classification_severity(latest.get("acmg_classification")),
    }
