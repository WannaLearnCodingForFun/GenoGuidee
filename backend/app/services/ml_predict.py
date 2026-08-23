"""Single source of truth for ML pathogenicity predictions.

predicted_class == argmax(probabilities)
confidence == probabilities[predicted_class]
sum(probabilities) == 1.0
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import numpy as np

log = logging.getLogger("genoguide")
REPO = Path(__file__).resolve().parents[3]
MODEL_DIR = REPO / "models" / "production"
REGISTRY_DIR = REPO / "models" / "registry"

CLASSES = ["benign", "likely_benign", "vus", "likely_pathogenic", "pathogenic"]
LABELS = {
    "pathogenic": "Pathogenic",
    "likely_pathogenic": "Likely Pathogenic",
    "vus": "VUS",
    "likely_benign": "Likely Benign",
    "benign": "Benign",
}


def _normalize(probs: dict[str, float]) -> dict[str, float]:
    out = {k: float(max(0.0, probs.get(k, 0.0))) for k in CLASSES}
    s = sum(out.values())
    if s <= 0:
        raise ValueError("probabilities are empty or all zero")
    return {k: round(v / s, 6) for k, v in out.items()}


def finalize_prediction(
    raw_probs: dict[str, float],
    *,
    model_name: str,
    model_version: str,
    dataset_version: str,
    feature_schema_version: str,
    calibrated: bool,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    probabilities = _normalize(raw_probs)
    predicted_class = max(probabilities, key=probabilities.get)
    confidence = probabilities[predicted_class]
    body = {
        "variant_id": None,
        "model": model_name,
        "model_name": model_name,
        "model_version": model_version,
        "training_dataset_version": dataset_version,
        "feature_schema_version": feature_schema_version,
        "probabilities": probabilities,
        "predicted_class": predicted_class,
        "predicted_class_label": LABELS[predicted_class],
        "top_class": LABELS[predicted_class],
        "top_class_key": predicted_class,
        "confidence": confidence,
        "calibrated": calibrated,
        "model_status": "ready",
        "engine": model_name,
    }
    if extra:
        body.update(extra)
    return body


@lru_cache(maxsize=1)
def load_production_bundle() -> Optional[dict[str, Any]]:
    """Prefer registered ClinVar XGBoost, then logreg, then unregistered xgb file."""
    preferred = [
        REGISTRY_DIR / "genoguide-tabular-xgboost-v0.1.0.json",
        REGISTRY_DIR / "genoguide-tabular-logreg-v0.1.0.json",
    ]
    for entry in preferred:
        if not entry.exists():
            continue
        meta = json.loads(entry.read_text())
        artifact = REPO / meta["artifact"] if meta.get("artifact") else None
        if artifact and artifact.exists():
            import joblib
            bundle = joblib.load(artifact)
            return {"meta": meta, **bundle}
    xgb = MODEL_DIR / "xgboost_gene_disjoint.joblib"
    if xgb.exists():
        import joblib
        bundle = joblib.load(xgb)
        return {
            "meta": {
                "model_id": "genoguide-xgboost-clinvar-v0.1.0",
                "artifact": str(xgb.relative_to(REPO)),
                "training_dataset": {"path": "research/data/processed/training_dataset.parquet"},
            },
            **bundle,
        }
    return None


def predict_from_annotation(annotation: dict[str, Any]) -> Optional[dict[str, Any]]:
    bundle = load_production_bundle()
    if bundle is None:
        return None
    from .interpret import _feature_vector

    features = bundle.get("features")
    if not features:
        return None
    X = _feature_vector(annotation, features)
    model = bundle["model"]
    raw = model.predict_proba(X)[0]
    labels = list(bundle.get("labels") or CLASSES)
    uncal = {l: float(x) for l, x in zip(labels, raw)}
    T = float(bundle.get("temperature") or 1.0)
    logp = np.log(np.clip(raw, 1e-12, 1.0)) / T
    logp -= logp.max()
    cal = np.exp(logp)
    cal = cal / cal.sum()
    calibrated = {l: float(x) for l, x in zip(labels, cal)}
    meta = bundle.get("meta") or {}
    return finalize_prediction(
        calibrated,
        model_name=str(meta.get("model_id") or "genoguide-xgboost-clinvar"),
        model_version=str(meta.get("model_id") or meta.get("registered") or "unknown"),
        dataset_version=str((meta.get("training_dataset") or {}).get("path") or "clinvar-training"),
        feature_schema_version="clinvar-tabular-v1",
        calibrated=True,
        extra={"uncalibrated_probabilities": uncal, "temperature": T},
    )


def smoke_inference() -> dict[str, Any]:
    """Tiny in-process check used by health. Does not invent a clinical call."""
    bundle = load_production_bundle()
    if bundle is None:
        return {"ok": False, "detail": "no production model artifact"}
    n = len(bundle.get("features") or [])
    X = np.zeros((1, n), dtype=np.float32)
    try:
        proba = bundle["model"].predict_proba(X)[0]
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
    if proba.shape[0] < 2 or not np.isfinite(proba).all():
        return {"ok": False, "detail": "invalid probability vector"}
    return {"ok": True, "detail": "inference executed", "n_classes": int(proba.shape[0])}
