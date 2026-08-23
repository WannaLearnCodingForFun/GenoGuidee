"""Honest component health for the demo and diagnose.sh.

Never report READY unless the component actually initialized.
Ngrok is OPTIONAL and is never required for local health.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config import DB_PATH, DEMO_MODE, MODEL_DIR

REPO = Path(__file__).resolve().parents[2]
_LOGREG = REPO / "models" / "production" / "logreg_gene_disjoint.joblib"


def _state(status: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "detail": detail, **extra}


def _acmg() -> dict[str, Any]:
    try:
        from .interpretation.acmg_v2 import CRITERIA_REGISTRY, ENGINE_VERSION
        return _state("READY", f"ACMG/AMP 2015 engine {ENGINE_VERSION}",
                      criteria=len(CRITERIA_REGISTRY), implementation="IMPLEMENTED")
    except Exception as exc:  # noqa: BLE001
        return _state("ERROR", f"{type(exc).__name__}: {exc}")


def _ml() -> dict[str, Any]:
    try:
        from .ml import esm_status, xgb_status
        esm = esm_status()
        xgb = xgb_status()
        from .services.ml_predict import load_production_bundle, smoke_inference
        bundle = load_production_bundle()
        smoke = smoke_inference()
        if bundle and smoke.get("ok"):
            meta = bundle.get("meta") or {}
            return _state(
                "READY",
                f"{meta.get('model_id', 'production model')} inference executed. "
                f"ESM-2 {esm.get('mode')}.",
                esm=esm, xgboost=xgb, smoke=smoke,
                implementation="IMPLEMENTED",
            )
        if xgb.get("ready"):
            mode = esm.get("mode") or "demo-precomputed"
            return _state(
                "DEGRADED",
                f"Only demo XGBoost is loaded. ESM-2 is {mode}. "
                "Research logreg artifact missing.",
                esm=esm, xgboost=xgb, research_logreg=False,
                implementation="DEMO",
            )
        return _state("NOT_CONFIGURED", smoke.get("detail") or "no ML artifact initialized",
                      esm=esm, xgboost=xgb, smoke=smoke)
    except Exception as exc:  # noqa: BLE001
        return _state("ERROR", f"{type(exc).__name__}: {exc}")


def _research() -> dict[str, Any]:
    try:
        from .interpretation.acmg_v2 import ENGINE_VERSION
        from .services.evidence import EvidenceService
        sources = EvidenceService().source_summary()
        available = sum(
            1 for key, value in sources.items()
            if key != "annotation_version" and str(value).startswith("AVAILABLE")
        )
        return _state("READY", f"{available} evidence source(s) available",
                      acmg_engine=ENGINE_VERSION, sources=sources)
    except Exception as exc:  # noqa: BLE001
        return _state("DEGRADED", f"research engine import failed: {type(exc).__name__}: {exc}")


def _probe_remote_therapy() -> dict[str, Any]:
    url = (os.environ.get("GENOGUIDE_DRUG_API_URL") or os.environ.get("THERAPY_API_BASE_URL") or "").strip()
    if not url:
        return {"ok": False, "detail": "no remote therapy URL configured"}
    try:
        import httpx
        probe = url.rstrip("/") + "/health"
        r = httpx.get(probe, timeout=1.5)
        return {"ok": r.status_code < 500, "status_code": r.status_code, "url": probe}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": "Therapy evidence service unavailable.", "error": type(exc).__name__}


def _therapy() -> dict[str, Any]:
    try:
        from .services.drug_recommendation import connector_status
        st = connector_status()
        remote = _probe_remote_therapy()
        if st.get("local_engine"):
            return _state(
                "READY",
                "local Medical_DrugRecommendation ranker",
                connector=st, remote=remote, implementation="LOCAL",
            )
        if remote.get("ok"):
            return _state("READY", "remote therapy API health check succeeded",
                          connector=st, remote=remote, implementation="REMOTE")
        if st.get("enabled") and st.get("url_configured"):
            return _state("DEGRADED", "Therapy evidence service unavailable.",
                          connector=st, remote=remote)
        return _state("NOT_CONFIGURED",
                      "local ranker disabled and no remote GENOGUIDE_DRUG_API_URL",
                      connector=st, remote=remote)
    except Exception as exc:  # noqa: BLE001
        return _state("ERROR", f"{type(exc).__name__}: {exc}")


def _datasets() -> dict[str, Any]:
    clin = REPO / "research" / "data" / "processed" / "clinvar_grch38.parquet"
    train = REPO / "research" / "data" / "processed" / "training_dataset.parquet"
    present = [p.name for p in (clin, train) if p.exists()]
    if clin.exists() and train.exists():
        return _state("READY", "ClinVar processed catalog and training matrix present",
                      files=present, implementation="LOCAL_CACHE")
    if present:
        return _state("DEGRADED", "partial dataset cache", files=present)
    return _state("NOT_CONFIGURED", "processed ClinVar/training files not downloaded")


def _database() -> dict[str, Any]:
    try:
        from . import clinical_db as C
        C.init()
        clinical = C.db_path()
        ledger = Path(DB_PATH)
        return _state(
            "READY",
            f"clinical {clinical.name}; ledger {ledger.name if ledger.exists() else 'pending'}",
            clinical=str(clinical),
            ledger=str(ledger),
            bytes=clinical.stat().st_size if clinical.exists() else 0,
        )
    except Exception as exc:  # noqa: BLE001
        return _state("ERROR", f"{type(exc).__name__}: {exc}")


def _vcf_parser() -> dict[str, Any]:
    try:
        from .bioinformatics.vcf import validate_vcf  # noqa: F401
        return _state("READY", "VCF validator + canonical iterator", implementation="IMPLEMENTED")
    except Exception as exc:  # noqa: BLE001
        return _state("ERROR", f"{type(exc).__name__}: {exc}")


def _knowledge_graph() -> dict[str, Any]:
    try:
        from . import clinical_db as C
        C.init()
        return _state("READY", "patient-derived entities/relationships", implementation="IMPLEMENTED")
    except Exception as exc:  # noqa: BLE001
        return _state("ERROR", f"{type(exc).__name__}: {exc}")


def _provenance() -> dict[str, Any]:
    try:
        from . import provenance
        stats = provenance.ledger_stats()
        return _state(
            "READY",
            "local hash-chained SQLite ledger (not Hyperledger Fabric)",
            stats=stats, implementation="IMPLEMENTED", fabric="FUTURE",
        )
    except Exception as exc:  # noqa: BLE001
        return _state("ERROR", f"{type(exc).__name__}: {exc}")


def _ngrok() -> dict[str, Any]:
    public = (os.environ.get("GENOGUIDE_PUBLIC_URL") or os.environ.get("GENOGUIDE_NGROK_URL") or "").strip()
    if not public:
        return _state("NOT_CONFIGURED", "optional — unset GENOGUIDE_PUBLIC_URL; local :8000 is enough")
    return _state("DEGRADED", "public URL configured but not probed from this process",
                  url=public.rstrip("/"))


def assemble_health(*, detailed: bool = False) -> dict[str, Any]:
    components = {
        "backend": _state("READY", "FastAPI process responding"),
        "acmg": _acmg(),
        "ml": _ml(),
        "research": _research(),
        "therapy": _therapy(),
        "database": _database(),
        "provenance": _provenance(),
        "vcf_parser": _vcf_parser(),
        "knowledge_graph": _knowledge_graph(),
        "ngrok": _ngrok(),
        "datasets": _datasets(),
    }
    rank = {"ERROR": 4, "OFFLINE": 3, "NOT_CONFIGURED": 2, "DEGRADED": 1, "READY": 0}
    critical = ("backend", "acmg")
    worst_critical = max(rank.get(components[k]["status"], 4) for k in critical)
    worst_all = max(rank.get(c["status"], 4) for c in components.values())
    if worst_critical >= 3:
        overall = "FAILED"
    elif worst_all >= 4:
        overall = "FAILED"
    elif worst_all >= 1:
        overall = "DEGRADED"
    else:
        overall = "READY"
    body: dict[str, Any] = {
        "status": overall,
        "ok": overall != "FAILED",
        "components": components,
        "demo_mode": DEMO_MODE,
        "model_dir": str(MODEL_DIR),
    }
    if detailed:
        body["notes"] = {
            "ngrok": "OPTIONAL — local ACMG/research/therapy do not require a tunnel",
            "esm2": "LIVE only when GENOGUIDE_MODE=live and fair-esm is installed",
            "fabric": "NOT IMPLEMENTED — provenance is a local hash chain",
            "therapy": "downstream decision support; never overrides ACMG",
        }
    return body
