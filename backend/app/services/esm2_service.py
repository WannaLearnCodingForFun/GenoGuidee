"""Cached ESM-2 inference. Never invents a protein sequence."""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

import numpy as np

log = logging.getLogger("genoguide")
_MODEL = None
_ALPHABET = None
_CONVERTER = None
_CACHE: dict[str, np.ndarray] = {}
MODEL_NAME = "esm2_t6_8M_UR50D"


def available() -> bool:
    try:
        import esm  # noqa: F401
        import torch  # noqa: F401
        return True
    except Exception:
        return False


def load() -> bool:
    global _MODEL, _ALPHABET, _CONVERTER
    if _MODEL is not None:
        return True
    if not available():
        return False
    import esm
    import torch

    _MODEL, _ALPHABET = esm.pretrained.esm2_t6_8M_UR50D()
    _MODEL.eval()
    if torch.backends.mps.is_available():
        _MODEL = _MODEL.to("mps")
    elif torch.cuda.is_available():
        _MODEL = _MODEL.to("cuda")
    _CONVERTER = _ALPHABET.get_batch_converter()
    log.info("[ESM2] loaded %s once (cached)", MODEL_NAME)
    return True


def _embed(seq: str) -> np.ndarray:
    key = hashlib.sha256(seq.encode()).hexdigest()
    if key in _CACHE:
        return _CACHE[key]
    import torch

    with torch.no_grad():
        _, _, toks = _CONVERTER([("s", seq)])
        toks = toks.to(next(_MODEL.parameters()).device)
        out = _MODEL(toks, repr_layers=[6])
        emb = out["representations"][6][0, 1:-1].mean(0).detach().cpu().numpy()
    _CACHE[key] = emb
    return emb


def represent(ref_seq: Optional[str], alt_seq: Optional[str], consequence: Optional[str] = None) -> dict[str, Any]:
    protein_ok = consequence in {None, "missense_variant", "missense", "synonymous_variant", "synonymous"}
    if not protein_ok:
        return {
            "availability": "NOT_APPLICABLE",
            "mode": "skipped",
            "model": MODEL_NAME,
            "reason": f"protein embedding is not appropriate for consequence={consequence}",
            "dims": 0,
            "embedding_preview": [],
            "delta_score": None,
        }
    if not ref_seq or not alt_seq:
        return {
            "availability": "SOURCE_NOT_CONFIGURED",
            "mode": "unavailable",
            "model": MODEL_NAME,
            "reason": "no reference/alternate protein sequence (need UniProt/MANE FASTA)",
            "dims": 0,
            "embedding_preview": [],
            "delta_score": None,
        }
    if not load():
        return {
            "availability": "NOT_INSTALLED",
            "mode": "unavailable",
            "model": MODEL_NAME,
            "reason": "torch/fair-esm are not installed in this environment",
            "dims": 0,
            "embedding_preview": [],
            "delta_score": None,
        }
    ref = _embed(ref_seq)
    alt = _embed(alt_seq)
    cos = float(np.dot(ref, alt) / ((np.linalg.norm(ref) * np.linalg.norm(alt)) + 1e-12))
    delta = float(np.linalg.norm(ref - alt))
    return {
        "availability": "AVAILABLE",
        "mode": "live",
        "model": MODEL_NAME,
        "dims": int(alt.shape[0]),
        "embedding_preview": [round(float(x), 4) for x in alt[:64]],
        "delta_score": round(delta, 4),
        "cosine_similarity": round(cos, 4),
    }
