"""Assemble patient genomic timeline payloads. Precomputed summaries live in SQLite."""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from .. import clinical_db as DB
from .longitudinal_compare import compare_snapshots, variant_history
from .risk_forecast import forecast_risk
from .trajectory_score import classify_trend, load_config, patient_genomic_risk_score
from .variant_normalize import canonical_id_from_record


def _obs_for_snapshot(snapshot_id: int) -> list[dict[str, Any]]:
    rows = DB.list_snapshot_observations(snapshot_id)
    for row in rows:
        crit = row.get("acmg_criteria")
        if isinstance(crit, str):
            try:
                row["acmg_criteria"] = json.loads(crit)
            except json.JSONDecodeError:
                row["acmg_criteria"] = [c for c in crit.split(",") if c]
    return rows


def _change_summary(cmp: dict[str, Any], risk: dict[str, Any] | None) -> str:
    c = cmp["counts"]
    parts = [
        f"Compared with the previous test, {c['newly_detected']} variant(s) were newly detected, "
        f"{c['persistent']} remained persistent, and {c['reclassified']} changed ACMG classification."
    ]
    if risk and risk.get("previous") is not None and risk.get("current") is not None:
        direction = "increased" if risk["delta"] > 0 else "decreased" if risk["delta"] < 0 else "was unchanged"
        parts.append(
            f"Overall genomic risk {direction} from {risk['previous']} to {risk['current']}."
        )
    contrib = cmp.get("reclassified")[:2] + cmp.get("newly_detected")[:2]
    if contrib:
        labels = []
        for item in contrib:
            gene = item.get("gene") or item.get("canonical_variant_id")
            if item.get("from"):
                labels.append(f"{gene} {item['from']}→{item['to']}")
            else:
                labels.append(str(gene))
        parts.append(f"Primary recorded contributors: {', '.join(labels)}.")
    parts.append("These are observed genomic changes only and require clinician review.")
    return " ".join(parts)


def build_timeline(patient_id: int) -> dict[str, Any]:
    snaps = DB.list_genomic_snapshots(patient_id)
    cfg = load_config()
    scores = [s.get("overall_risk_score") for s in snaps if s.get("overall_risk_score") is not None]
    score_vals = [float(s) for s in scores]
    trend = classify_trend(score_vals, cfg) if score_vals else "UNCERTAIN"
    baseline = score_vals[0] if score_vals else None
    current = score_vals[-1] if score_vals else None
    delta = round(current - baseline, 2) if baseline is not None and current is not None else None
    pct = None
    if baseline not in (None, 0) and current is not None:
        pct = round((current - baseline) / abs(baseline) * 100.0, 2)

    prev_obs: list[dict[str, Any]] | None = None
    timeline = []
    last_cmp = None
    for snap in snaps:
        obs = _obs_for_snapshot(int(snap["id"]))
        cmp = compare_snapshots(
            obs,
            prev_obs,
            current_risk=snap.get("overall_risk_score"),
            previous_risk=timeline[-1]["overall_risk_score"] if timeline else None,
        ) if prev_obs is not None else None
        node_trend = "UNCERTAIN"
        if timeline and snap.get("overall_risk_score") is not None and timeline[-1].get("overall_risk_score") is not None:
            node_trend = classify_trend(
                [float(timeline[-1]["overall_risk_score"]), float(snap["overall_risk_score"])],
                cfg,
            )
        elif len(timeline) == 0:
            node_trend = "UNCERTAIN"
        timeline.append({
            **{k: snap[k] for k in snap if k != "payload_json"},
            "trend": node_trend,
            "comparison": cmp,
        })
        if cmp:
            last_cmp = cmp
        prev_obs = obs

    variants = build_variant_summaries(patient_id)
    projection = forecast_risk(score_vals, cfg)
    summary = None
    if last_cmp:
        summary = _change_summary(last_cmp, last_cmp.get("risk_change"))

    payload = {
        "patient_id": patient_id,
        "synthetic": any(s.get("sample_identifier") == "SYNTHETIC-DEMO" for s in snaps),
        "baseline_score": baseline,
        "current_score": current,
        "delta": delta,
        "percentage_change": pct,
        "trend": trend,
        "snapshots": timeline,
        "variants": variants,
        "latest_comparison": last_cmp,
        "change_summary": summary,
        "projection": projection,
        "scoring": {
            "variant_weights": cfg["variant_trajectory"],
            "patient_weights": cfg["patient_risk"],
            "risk_threshold": cfg["projection"]["risk_threshold"],
        },
        "outcome": {
            "supported": False,
            "message": "No validated outcome prediction available.",
            "note": (
                "GenoGuide does not estimate time-to-death from a genomic variant. "
                "The projection below is a risk-score trajectory only."
            ),
        },
        "disclaimer": (
            "Decision support only. Historical snapshots are immutable. "
            "ML probabilities do not override ACMG classification."
        ),
    }
    DB.save_trajectory_summary(patient_id, payload)
    return payload


def build_variant_summaries(patient_id: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in DB.list_patient_genomic_observations(patient_id):
        try:
            key = canonical_id_from_record(row)
        except ValueError:
            continue
        row["canonical_variant_id"] = key
        grouped[key].append(row)
    out = [variant_history(pts) for pts in grouped.values()]
    out.sort(key=lambda v: (v.get("severity") or 0, v.get("variant_trajectory_score") or 0), reverse=True)
    return out


def snapshot_detail(patient_id: int, snapshot_id: int) -> dict[str, Any]:
    snap = DB.get_genomic_snapshot(snapshot_id)
    if not snap or int(snap["patient_id"]) != int(patient_id):
        raise KeyError(snapshot_id)
    obs = _obs_for_snapshot(snapshot_id)
    snaps = DB.list_genomic_snapshots(patient_id)
    prev = None
    for i, s in enumerate(snaps):
        if int(s["id"]) == int(snapshot_id) and i > 0:
            prev = _obs_for_snapshot(int(snaps[i - 1]["id"]))
            break
    cmp = compare_snapshots(obs, prev, current_risk=snap.get("overall_risk_score"))
    return {**snap, "observations": obs, "comparison": cmp}


def variant_trajectory(patient_id: int, canonical_id: str) -> dict[str, Any]:
    for item in build_variant_summaries(patient_id):
        if item.get("canonical_variant_id") == canonical_id:
            return item
    raise KeyError(canonical_id)


def therapy_relevance(patient_id: int) -> dict[str, Any]:
    """Surface therapy notes when ACMG class changes across tests. No prescriptions."""
    variants = build_variant_summaries(patient_id)
    notes = []
    for v in variants:
        hist = [c for c in (v.get("classification_history") or []) if c]
        uniq = []
        for c in hist:
            if not uniq or uniq[-1] != c:
                uniq.append(c)
        if len(uniq) >= 2:
            notes.append({
                "canonical_variant_id": v.get("canonical_variant_id"),
                "gene": v.get("gene"),
                "classification_path": uniq,
                "note": (
                    "Therapy relevance changed following variant reclassification. "
                    "Potentially relevant therapy only — requires clinician review. "
                    "Not a treatment recommendation."
                ),
            })
    stored = []
    con_rows = DB.list_therapy_results(patient_id)
    for row in con_rows:
        payload = row.get("payload") or {}
        stored.append({
            "created_at": row.get("created_at"),
            "items": payload.get("recommendations") or payload.get("therapies") or payload,
        })
    return {
        "patient_id": patient_id,
        "reclassification_notes": notes,
        "stored_rankings": stored,
        "disclaimer": (
            "Potentially relevant therapy based on annotated variants and the curated "
            "Medical_DrugRecommendation / CIViC evidence set. Requires clinician review."
        ),
    }


def change_summary(patient_id: int) -> dict[str, Any]:
    tl = build_timeline(patient_id)
    return {
        "patient_id": patient_id,
        "text": tl.get("change_summary"),
        "comparison": tl.get("latest_comparison"),
        "trend": tl.get("trend"),
        "delta": tl.get("delta"),
    }
