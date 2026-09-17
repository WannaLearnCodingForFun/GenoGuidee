"""Live feature-flag reads. Existing routes never consult these."""
from __future__ import annotations

import os

FLAG_DEFAULTS: dict[str, bool] = {
    "ENABLE_REANALYSIS": True,
    "ENABLE_EVIDENCE_GRAPH": True,
    "ENABLE_HUMAN_REVIEW": True,
    "ENABLE_PHENOPACKET": True,
    "ENABLE_INHERITANCE_SOLVER": True,
    "ENABLE_VARIANT_SIMULATOR": True,
    "ENABLE_COHORT_MODE": False,
    "ENABLE_MODEL_MONITORING": True,
    "ENABLE_INTERPRETATION_VERSIONING": True,
    "ENABLE_WATCHLIST": True,
    "ENABLE_PHENOTYPE_ENGINE": True,
    "ENABLE_EXPLANATION": True,
    "ENABLE_PROVENANCE_UPGRADE": True,
    "ENABLE_EVIDENCE_TIMELINE": True,
}

_TRUE = {"1", "true", "yes", "on"}


def enabled(name: str) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return bool(FLAG_DEFAULTS.get(name, False))
    return raw.strip().lower() in _TRUE


def snapshot() -> dict[str, bool]:
    return {k: enabled(k) for k in FLAG_DEFAULTS}
