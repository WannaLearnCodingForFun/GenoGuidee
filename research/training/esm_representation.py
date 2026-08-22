"""
Frozen ESM-2 protein representation (section 24–25).

This module is an INTERFACE + optional live path. It does NOT download weights
unless fair-esm/torch are installed AND the caller opts in.

Modes:
  unavailable  — torch/fair-esm not installed (default on a research laptop)
  frozen       — esm2_t6_8M_UR50D forward pass, weights frozen
  demo_hash    — deterministic hash vector (labeled as such; never a substitute
                 for a trained embedding in published metrics)

Sequence construction requires a real protein sequence. Without UniProt/MANE
FASTA this module returns availability=SOURCE_NOT_CONFIGURED rather than
inventing a 41-aa window from a hash (that hack exists only in the legacy
demo `app/ml.py` and must not leak into research reports).
"""
from __future__ import annotations

import hashlib
from typing import Any, Optional

import numpy as np

ESM_MODELS = {
    "esm2_t6_8M_UR50D": {"layers": 6, "embed_dim": 320, "params": "8M (public card, not loaded here)"},
    "esm2_t12_35M_UR50D": {"layers": 12, "embed_dim": 480, "params": "35M"},
    "esm2_t30_150M_UR50D": {"layers": 30, "embed_dim": 640, "params": "150M"},
}

DEFAULT_MODEL = "esm2_t6_8M_UR50D"


def esm_available() -> bool:
    try:
        import esm  # noqa: F401
        import torch  # noqa: F401
        return True
    except Exception:
        return False


def window(seq: str, aa_pos_1based: int, flank: int = 32) -> str:
    i = max(aa_pos_1based - 1, 0)
    return seq[max(0, i - flank): i + 1 + flank]


def delta_features(emb_ref: np.ndarray, emb_alt: np.ndarray) -> dict[str, float]:
    a, b = emb_ref.astype(np.float64), emb_alt.astype(np.float64)
    na, nb = np.linalg.norm(a) + 1e-12, np.linalg.norm(b) + 1e-12
    cosine = float(np.dot(a, b) / (na * nb))
    l2 = float(np.linalg.norm(a - b))
    return {
        "cosine_similarity": cosine,
        "l2_distance": l2,
        "delta_mean": float((a - b).mean()),
    }


def represent(
    ref_seq: Optional[str],
    alt_seq: Optional[str],
    *,
    model_name: str = DEFAULT_MODEL,
    pooling: str = "mean",
    allow_demo_hash: bool = False,
) -> dict[str, Any]:
    if not ref_seq or not alt_seq:
        return {
            "availability": "SOURCE_NOT_CONFIGURED",
            "reason": "no protein sequence provided (need UniProt/MANE FASTA)",
            "model": model_name,
        }
    if esm_available():
        return {
            "availability": "INTERFACE_READY",
            "mode": "frozen",
            "model": model_name,
            "pooling": pooling,
            "note": "Call load_esm() in a training job to run the forward pass. "
                    "Weights are never auto-downloaded by interpret().",
            "seq_len_ref": len(ref_seq),
            "seq_len_alt": len(alt_seq),
        }
    if allow_demo_hash:
        rng = np.random.default_rng(int(hashlib.sha256(ref_seq.encode()).hexdigest()[:8], 16))
        dim = ESM_MODELS[model_name]["embed_dim"]
        ref = rng.normal(size=dim)
        alt = rng.normal(size=dim)
        return {
            "availability": "DEMO_HASH",
            "warning": "SYNTHETIC hash embedding — not valid for published metrics",
            "model": model_name,
            **delta_features(ref, alt),
        }
    return {
        "availability": "NOT_INSTALLED",
        "reason": "torch/fair-esm not installed; pip install -r backend/requirements-live.txt",
        "model": model_name,
    }
