"""Model drift / OOD monitoring. Never silently retrains."""
from __future__ import annotations

import math
from typing import Any, Optional

from . import store

CLASSES = ["benign", "likely_benign", "vus", "likely_pathogenic", "pathogenic"]


def entropy(probs: dict[str, float]) -> float:
    e = 0.0
    for p in probs.values():
        if p and p > 0:
            e -= float(p) * math.log(float(p))
    return e


def ood_from_prediction(ml: dict[str, Any]) -> dict[str, Any]:
    ood = ml.get("ood") if isinstance(ml, dict) else None
    probs = (ml or {}).get("calibrated_probabilities") or (ml or {}).get("probabilities") or {}
    ent = entropy(probs) if probs else None
    max_p = max(probs.values()) if probs else None
    state = None
    score = None
    if isinstance(ood, dict):
        state = ood.get("state")
        score = ood.get("distance") or ood.get("score")
    if state is None and max_p is not None:
        if max_p < 0.4:
            state = "OUT_OF_DISTRIBUTION"
            score = 1.0 - max_p
        elif max_p < 0.55:
            state = "LOW_CONFIDENCE"
            score = 1.0 - max_p
        else:
            state = "IN_DISTRIBUTION"
            score = 1.0 - max_p
    review = state == "OUT_OF_DISTRIBUTION"
    return {
        "prediction": (ml or {}).get("top_class"),
        "calibrated_probability": max_p,
        "entropy": ent,
        "uncertainty": 1.0 - max_p if max_p is not None else None,
        "OOD_score": score,
        "OOD_state": state,
        "model_version": (ml or {}).get("model_version") or (ml or {}).get("model_id"),
        "human_review_required": review,
    }


def snapshot(current: list[dict[str, Any]], training_prior: Optional[dict[str, float]] = None) -> dict[str, Any]:
    """current: list of prediction dicts with top_class / probabilities / gene / consequence."""
    n = len(current) or 1
    class_hist = {c: 0 for c in CLASSES}
    genes: dict[str, int] = {}
    missing = 0
    ood_n = 0
    entropies = []
    for p in current:
        top = str(p.get("top_class") or p.get("predicted_class") or "vus").lower().replace(" ", "_")
        if top in class_hist:
            class_hist[top] += 1
        g = p.get("gene")
        if g:
            genes[g] = genes.get(g, 0) + 1
        if p.get("missing"):
            missing += 1
        info = ood_from_prediction(p)
        if info["OOD_state"] == "OUT_OF_DISTRIBUTION":
            ood_n += 1
        if info["entropy"] is not None:
            entropies.append(info["entropy"])
    current_dist = {k: v / n for k, v in class_hist.items()}
    prior = training_prior or {c: 0.2 for c in CLASSES}
    tv = 0.5 * sum(abs(current_dist[c] - float(prior.get(c, 0.2))) for c in CLASSES)
    ood_rate = ood_n / n
    miss_rate = missing / n
    if tv > 0.35 or ood_rate > 0.2:
        level = "HIGH"
    elif tv > 0.15 or ood_rate > 0.08:
        level = "MODERATE"
    else:
        level = "LOW"
    payload = {
        "n": len(current),
        "class_distribution": current_dist,
        "training_prior": prior,
        "total_variation": round(tv, 4),
        "ood_rate": round(ood_rate, 4),
        "missingness": round(miss_rate, 4),
        "mean_entropy": round(sum(entropies) / len(entropies), 4) if entropies else None,
        "gene_distribution": sorted(genes.items(), key=lambda kv: -kv[1])[:30],
        "drift_level": level,
        "action": "REVIEW MODEL" if level == "HIGH" else "monitor",
        "retrained": False,
    }
    store.execute(
        "INSERT INTO model_monitor_snapshots (created_at, drift_level, payload_json) VALUES (?,?,?)",
        (store.now(), level, store.dumps(payload)),
    )
    return payload


def latest() -> Optional[dict[str, Any]]:
    row = store.execute(
        "SELECT created_at, drift_level, payload_json FROM model_monitor_snapshots ORDER BY id DESC LIMIT 1",
        fetch="one",
    )
    if not row:
        return None
    body = store.loads(row[2], {})
    body["created_at"] = row[0]
    body["drift_level"] = row[1]
    return body
