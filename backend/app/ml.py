"""
GenoGuide ML pipeline: ESM-2 representation -> structured features -> XGBoost.

DEMO_MODE (default, offline-safe):
  - ESM-2 embeddings are deterministic precomputed vectors (seeded from the
    variant identity) with a stored per-variant embedding-shift score.
  - Showcase variants return curated precomputed probabilities so the live
    demo is exactly reproducible. Cohort variants always run real XGBoost.

LIVE_MODE (GENOGUIDE_MODE=live, requires torch + fair-esm):
  - Real esm2_t6_8M_UR50D inference over the variant's stored sequence context;
    the embedding shift is the cosine distance between ref and alt embeddings.

The XGBoost model itself is always real: trained once on a structured,
class-conditioned synthetic genomic feature set and persisted to disk.
"""
from __future__ import annotations

import hashlib
import random
from typing import Any

import numpy as np

from .config import DEMO_MODE, ESM_EMBED_DIM, ESM_MODEL_NAME, MODEL_DIR, MODEL_VERSION
from .dataset import _sample_variant

CLASSES = ["pathogenic", "likely_pathogenic", "vus", "likely_benign", "benign"]
CLASS_LABELS = {
    "pathogenic": "Pathogenic",
    "likely_pathogenic": "Likely Pathogenic",
    "vus": "VUS",
    "likely_benign": "Likely Benign",
    "benign": "Benign",
}

_CONSEQUENCE_RANK = {
    "frameshift": 6, "nonsense": 6, "splice_donor": 5, "splice_acceptor": 5,
    "inframe_deletion": 4, "missense": 3, "synonymous": 1, "intronic": 0,
}

_AA = "ACDEFGHIKLMNPQRSTVWY"

# ---------------------------------------------------------------------------
# ESM-2 representation
# ---------------------------------------------------------------------------

_esm_live_model = None
_esm_live_ready = False

if not DEMO_MODE:
    try:  # pragma: no cover - optional heavy dependency
        import esm as _fair_esm
        import torch as _torch

        _esm_live_model, _esm_alphabet = _fair_esm.pretrained.esm2_t6_8M_UR50D()
        _esm_live_model.eval()
        _esm_batch_converter = _esm_alphabet.get_batch_converter()
        _esm_live_ready = True
    except Exception:
        _esm_live_ready = False


def _sequence_context(variant: dict[str, Any]) -> tuple[str, str]:
    """Deterministic 41-aa demo sequence context (ref, alt) for a variant."""
    seed = int(hashlib.sha256(f"{variant['gene']}|{variant['hgvs_c']}".encode()).hexdigest(), 16)
    rng = random.Random(seed)
    ref = "".join(rng.choice(_AA) for _ in range(41))
    alt = list(ref)
    if variant["consequence"] in ("frameshift", "nonsense"):
        alt = alt[:20]  # truncation
    else:
        alt[20] = rng.choice(_AA.replace(ref[20], ""))
    return ref, "".join(alt)


def _deterministic_embedding(variant: dict[str, Any]) -> np.ndarray:
    seed = int(hashlib.sha256(variant["id"].encode()).hexdigest()[:12], 16)
    rng = np.random.default_rng(seed)
    emb = rng.normal(0, 0.6, ESM_EMBED_DIM).astype(np.float32)
    # Encode the stored embedding-shift score into the vector's leading band
    # so visualizations correlate with the biological signal.
    emb[:24] += float(variant.get("esm_delta") or 0.0) * 2.2
    return emb


def esm_representation(variant: dict[str, Any]) -> dict[str, Any]:
    if _esm_live_ready:  # LIVE mode with fair-esm available
        import torch

        ref_seq, alt_seq = _sequence_context(variant)
        with torch.no_grad():
            _, _, toks = _esm_batch_converter([("ref", ref_seq), ("alt", alt_seq)])
            out = _esm_live_model(toks, repr_layers=[6])
            reps = out["representations"][6].mean(dim=1)
        ref_emb, alt_emb = reps[0].numpy(), reps[1].numpy()
        cos = float(np.dot(ref_emb, alt_emb) / (np.linalg.norm(ref_emb) * np.linalg.norm(alt_emb) + 1e-9))
        delta = float(np.clip((1.0 - cos) * 12.0, 0.0, 1.0))
        return {
            "mode": "live",
            "model": ESM_MODEL_NAME,
            "dims": int(alt_emb.shape[0]),
            "embedding_preview": [round(float(x), 4) for x in alt_emb[:64]],
            "delta_score": round(delta, 3),
        }

    emb = _deterministic_embedding(variant)
    return {
        "mode": "demo-precomputed",
        "model": ESM_MODEL_NAME,
        "dims": ESM_EMBED_DIM,
        "embedding_preview": [round(float(x), 4) for x in emb[:64]],
        "delta_score": float(variant.get("esm_delta") or 0.0),
    }


def esm_status() -> dict[str, Any]:
    return {
        "ready": True,
        "mode": "live" if _esm_live_ready else "demo-precomputed",
        "model": ESM_MODEL_NAME,
        "dims": ESM_EMBED_DIM,
    }

# ---------------------------------------------------------------------------
# XGBoost classifier
# ---------------------------------------------------------------------------

_MODEL_PATH = MODEL_DIR / "xgb_pathogenicity.json"
_xgb_model = None
_xgb_val_accuracy: float | None = None


def _features(v: dict[str, Any], esm_delta: float) -> list[float]:
    revel = v.get("revel")
    if revel is None:
        rank = _CONSEQUENCE_RANK.get(v.get("consequence"), 0)
        revel = 0.9 if rank >= 5 else (0.5 if rank >= 4 else 0.1)
    functional = {"damaging": 1.0, "benign": -1.0}.get(v.get("functional_evidence"), 0.0)
    return [
        float(_CONSEQUENCE_RANK.get(v.get("consequence"), 0)),
        float(np.log10((v.get("gnomad_af") or 0.0) + 1e-8)),
        float(v.get("cadd") or 0.0),
        float(revel),
        float(v.get("spliceai") or 0.0),
        float(v.get("phylop") or 0.0),
        1.0 if v.get("hotspot_domain") else 0.0,
        1.0 if v.get("lof_mechanism") else 0.0,
        float(esm_delta),
        functional,
        1.0 if v.get("segregation") else 0.0,
    ]


FEATURE_NAMES = [
    "consequence_severity", "log10_gnomad_af", "cadd", "revel_or_imputed",
    "spliceai", "phylop", "hotspot_domain", "lof_mechanism",
    "esm2_delta_score", "functional_evidence", "segregation",
]


def _build_training_set() -> tuple[np.ndarray, np.ndarray]:
    rng = random.Random(1337)
    xs, ys = [], []
    for label_idx, target in enumerate(CLASSES):
        for i in range(600):
            v = _sample_variant(rng, 90000 + i, target)
            xs.append(_features(v, v["esm_delta"]))
            ys.append(label_idx)
    return np.asarray(xs, dtype=np.float32), np.asarray(ys, dtype=np.int32)


def init_xgboost() -> None:
    global _xgb_model, _xgb_val_accuracy
    import xgboost as xgb
    from sklearn.metrics import accuracy_score
    from sklearn.model_selection import train_test_split

    model = xgb.XGBClassifier(
        objective="multi:softprob", num_class=len(CLASSES),
        n_estimators=150, max_depth=4, learning_rate=0.1,
        subsample=0.9, colsample_bytree=0.9, random_state=42,
        eval_metric="mlogloss",
    )
    X, y = _build_training_set()
    X_tr, X_va, y_tr, y_va = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    if _MODEL_PATH.exists():
        model.fit(X_tr[:50], y_tr[:50])  # initialize sklearn wrapper shape
        model.load_model(_MODEL_PATH)
    else:
        model.fit(X_tr, y_tr)
        model.save_model(_MODEL_PATH)
    _xgb_val_accuracy = float(accuracy_score(y_va, model.predict(X_va)))
    _xgb_model = model


def xgb_status() -> dict[str, Any]:
    return {
        "ready": _xgb_model is not None,
        "model_version": MODEL_VERSION,
        "validation_accuracy": round(_xgb_val_accuracy, 3) if _xgb_val_accuracy else None,
        "n_features": len(FEATURE_NAMES),
    }


def predict(variant: dict[str, Any], esm_delta: float) -> dict[str, Any]:
    """Pathogenicity probabilities. Curated showcase variants use precomputed
    probabilities in DEMO_MODE (reproducible demo); everything else is live XGBoost."""
    if DEMO_MODE and variant.get("demo_probs"):
        probs = dict(variant["demo_probs"])
        engine = "precomputed-demo"
    else:
        assert _xgb_model is not None, "XGBoost model not initialized"
        x = np.asarray([_features(variant, esm_delta)], dtype=np.float32)
        raw = _xgb_model.predict_proba(x)[0]
        probs = {cls: round(float(p), 4) for cls, p in zip(CLASSES, raw)}
        engine = "xgboost-live"

    top_key = max(probs, key=probs.get)
    return {
        "probabilities": probs,
        "top_class": CLASS_LABELS[top_key],
        "top_class_key": top_key,
        "confidence": round(float(probs[top_key]), 4),
        "engine": engine,
        "model_version": MODEL_VERSION,
        "feature_names": FEATURE_NAMES,
        "features": _features(variant, esm_delta),
    }
