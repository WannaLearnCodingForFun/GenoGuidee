"""Interpretable variant and patient risk scores. Weights live in configs/longitudinal.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO / "configs" / "longitudinal.yaml"

_DEFAULT = {
    "classification_severity": {
        "Pathogenic": 1.0,
        "Likely Pathogenic": 0.8,
        "VUS": 0.45,
        "Likely Benign": 0.15,
        "Benign": 0.05,
        "NOT_EVALUABLE": 0.2,
    },
    "variant_trajectory": {
        "pathogenicity": 0.30,
        "classification": 0.28,
        "vaf_trend": 0.16,
        "persistence": 0.14,
        "evidence_confidence": 0.12,
    },
    "patient_risk": {
        "pathogenic": 1.00,
        "likely_pathogenic": 0.75,
        "vus": 0.35,
        "likely_benign": 0.08,
        "benign": 0.03,
        "vaf_floor": 0.25,
        "confidence_floor": 0.20,
    },
    "trend": {
        "stable_abs_delta": 3.0,
        "mixed_reversal": 6.0,
        "min_snapshots_for_trend": 2,
        "min_snapshots_for_forecast": 3,
        "prefer_forecast": 4,
    },
    "projection": {"risk_threshold": 70, "horizon": 3, "unreliable_r2": 0.15},
}


def load_config() -> dict[str, Any]:
    if CONFIG_PATH.is_file():
        data = yaml.safe_load(CONFIG_PATH.read_text()) or {}
        merged = dict(_DEFAULT)
        for key, val in data.items():
            if isinstance(val, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **val}
            else:
                merged[key] = val
        return merged
    return dict(_DEFAULT)


def _cls_key(label: str | None) -> str:
    raw = (label or "").strip()
    aliases = {
        "p": "Pathogenic",
        "lp": "Likely Pathogenic",
        "likely pathogenic": "Likely Pathogenic",
        "vus": "VUS",
        "uncertain_significance": "VUS",
        "lb": "Likely Benign",
        "likely benign": "Likely Benign",
        "b": "Benign",
    }
    return aliases.get(raw.lower(), raw or "VUS")


def classification_severity(label: str | None, cfg: dict[str, Any] | None = None) -> float:
    cfg = cfg or load_config()
    return float(cfg["classification_severity"].get(_cls_key(label), 0.3))


def variant_trajectory_score(
    *,
    pathogenicity_probability: float | None,
    acmg_classification: str | None,
    vaf: float | None,
    vaf_slope: float | None,
    detection_rate: float | None,
    confidence: float | None,
    annotation_complete: float | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    w = cfg["variant_trajectory"]
    p_hat = max(0.0, min(1.0, float(pathogenicity_probability or 0.0)))
    cls = classification_severity(acmg_classification, cfg)
    vaf_c = 0.5
    if vaf_slope is not None:
        vaf_c = max(0.0, min(1.0, 0.5 + float(vaf_slope) * 2.0))
    elif vaf is not None:
        vaf_c = max(0.0, min(1.0, float(vaf)))
    persist = max(0.0, min(1.0, float(detection_rate if detection_rate is not None else 0.5)))
    ev = max(0.0, min(1.0, float(confidence if confidence is not None else 0.4)))
    if annotation_complete is not None:
        ev = (ev + max(0.0, min(1.0, float(annotation_complete)))) / 2.0
    components = {
        "pathogenicity": round(p_hat * 100, 4),
        "classification": round(cls * 100, 4),
        "vaf_trend": round(vaf_c * 100, 4),
        "persistence": round(persist * 100, 4),
        "evidence_confidence": round(ev * 100, 4),
    }
    score = (
        components["pathogenicity"] * w["pathogenicity"]
        + components["classification"] * w["classification"]
        + components["vaf_trend"] * w["vaf_trend"]
        + components["persistence"] * w["persistence"]
        + components["evidence_confidence"] * w["evidence_confidence"]
    )
    return {
        "variant_trajectory_score": round(max(0.0, min(100.0, score)), 2),
        "components": components,
        "weights": dict(w),
        "formula": (
            "0–100 = pathogenicity*w_p + classification*w_c + vaf_trend*w_v "
            "+ persistence*w_r + evidence_confidence*w_e"
        ),
    }


def patient_genomic_risk_score(observations: list[dict[str, Any]], cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Weighted aggregation of clinically relevant variants. Not a mean of all rows."""
    cfg = cfg or load_config()
    weights = cfg["patient_risk"]
    class_w = {
        "Pathogenic": weights["pathogenic"],
        "Likely Pathogenic": weights["likely_pathogenic"],
        "VUS": weights["vus"],
        "Likely Benign": weights["likely_benign"],
        "Benign": weights["benign"],
    }
    numer = 0.0
    denom = 0.0
    contributors: list[dict[str, Any]] = []
    for obs in observations:
        if obs.get("detected") is False:
            continue
        cls = _cls_key(obs.get("acmg_classification") or obs.get("clinical_significance"))
        cw = class_w.get(cls, 0.2)
        vaf = obs.get("allele_frequency")
        vaf = float(vaf) if vaf is not None else 0.4
        conf = obs.get("confidence")
        conf = float(conf) if conf is not None else 0.5
        p_hat = obs.get("pathogenicity_probability")
        p_hat = float(p_hat) if p_hat is not None else classification_severity(cls, cfg)
        vaf_w = weights["vaf_floor"] + (1 - weights["vaf_floor"]) * max(0.0, min(1.0, vaf))
        conf_w = weights["confidence_floor"] + (1 - weights["confidence_floor"]) * max(0.0, min(1.0, conf))
        w = cw * vaf_w * conf_w
        raw = p_hat * 100.0
        numer += raw * w
        denom += w
        contributors.append({
            "canonical_variant_id": obs.get("canonical_variant_id"),
            "gene": obs.get("gene"),
            "classification": cls,
            "weight": round(w, 4),
            "contribution": round(raw * w, 4),
        })
    if denom <= 0:
        return {
            "patient_genomic_risk_score": None,
            "confidence_score": 0.0,
            "n_variants": 0,
            "contributors": [],
            "method": "weighted_acmg_vaf_confidence",
        }
    score = max(0.0, min(100.0, numer / denom))
    top = sorted(contributors, key=lambda c: c["contribution"], reverse=True)[:8]
    return {
        "patient_genomic_risk_score": round(score, 2),
        "confidence_score": round(min(1.0, denom / max(1.0, len(observations))), 3),
        "n_variants": len(observations),
        "contributors": top,
        "method": "weighted_acmg_vaf_confidence",
        "weights": weights,
    }


def classify_trend(scores: list[float], cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or load_config()
    need = int(cfg["trend"]["min_snapshots_for_trend"])
    if len(scores) < need:
        return "UNCERTAIN"
    stable = float(cfg["trend"]["stable_abs_delta"])
    mixed = float(cfg["trend"]["mixed_reversal"])
    delta = scores[-1] - scores[0]
    ups = downs = 0
    for a, b in zip(scores, scores[1:]):
        step = b - a
        if step > stable:
            ups += 1
        elif step < -stable:
            downs += 1
    if ups and downs and abs(delta) < mixed:
        return "MIXED"
    if abs(delta) <= stable:
        return "STABLE"
    return "WORSENING" if delta > 0 else "IMPROVING"
