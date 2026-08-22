"""GenoGuide backend — FastAPI application."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import provenance
from .acmg import classify
from .clinical import analyze_variant_for_patient, build_knowledge_graph
from .config import (
    CONTRACT_CONSENT,
    CONTRACT_INTERPRETATION,
    DEMO_MODE,
    EVIDENCE_VERSION,
    MODEL_VERSION,
)
from .dataset import ALL_VARIANTS, PATIENTS, PATIENTS_BY_ID, VARIANTS_BY_ID
from .ml import esm_representation, esm_status, init_xgboost, predict, xgb_status

PATHOGENIC_SPECTRUM = {"Pathogenic", "Likely Pathogenic"}
BENIGN_SPECTRUM = {"Benign", "Likely Benign"}


def _bucket(cls: str) -> str:
    if cls in PATHOGENIC_SPECTRUM:
        return "pathogenic-spectrum"
    if cls in BENIGN_SPECTRUM:
        return "benign-spectrum"
    return "uncertain"


def _seed_ledger() -> None:
    if provenance.ledger_stats()["total_blocks"] > 0:
        return
    for p in PATIENTS:
        provenance.record_consent(p["id"], p["consent_scope"])
    # Seed one verified interpretation per patient's primary variant so the
    # provenance page is populated before any live analysis is run.
    for p in PATIENTS:
        v = VARIANTS_BY_ID[p["primary_variant_id"]]
        acmg = classify(v)
        esm = esm_representation(v)
        ml = predict(v, esm["delta_score"])
        status = "CONCORDANT" if _bucket(ml["top_class"]) == _bucket(acmg["classification"]) else "DISCORDANT"
        provenance.record_interpretation(
            p["id"], v["id"], f"{v['gene']} {v['hgvs_c']}", acmg["classification"],
            status, acmg["met_criteria"], ml["top_class"],
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    provenance.init_ledger()
    init_xgboost()
    _seed_ledger()
    yield


app = FastAPI(title="GenoGuide API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Drug Recommendation Module Router Integration
# ---------------------------------------------------------------------------
import sys
from pathlib import Path
_med_dir = Path(__file__).resolve().parent.parent.parent / "Medical_DrugRecommendation"
if str(_med_dir) not in sys.path:
    sys.path.insert(0, str(_med_dir))

try:
    from api.routes import router as drug_rec_router
    app.include_router(drug_rec_router)
except Exception as _e:
    print(f"Notice: Drug recommendation router load error: {_e}")


# ---------------------------------------------------------------------------
# System status / overview
# ---------------------------------------------------------------------------

@app.get("/api/status")
def status() -> dict[str, Any]:
    ledger = provenance.ledger_stats()
    return {
        "mode": "DEMO_MODE" if DEMO_MODE else "LIVE_MODE",
        "components": [
            {"name": "ESM-2", "ready": True, "detail": esm_status()},
            {"name": "XGBoost", "ready": xgb_status()["ready"], "detail": xgb_status()},
            {"name": "ACMG Engine", "ready": True,
             "detail": {"framework": "ACMG/AMP 2015", "criteria": 13, "deterministic": True}},
            {"name": "Provenance", "ready": True, "detail": ledger},
        ],
        "model_version": MODEL_VERSION,
        "evidence_version": EVIDENCE_VERSION,
    }


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    ledger = provenance.ledger_stats()
    return {
        "patients": len(PATIENTS),
        "variants_analyzed": sum(p["genome_stats"]["total_variants"] for p in PATIENTS),
        "high_priority_variants": sum(p["genome_stats"]["prioritized"] for p in PATIENTS),
        "verified_interpretations": ledger["interpretations_recorded"],
        "dataset_variants": len(ALL_VARIANTS),
        "showcase_variants": sum(1 for v in ALL_VARIANTS if v["showcase"]),
    }

# ---------------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------------

@app.get("/api/variants")
def list_variants() -> list[dict[str, Any]]:
    return [
        {
            "id": v["id"], "gene": v["gene"], "hgvs_c": v["hgvs_c"], "hgvs_p": v["hgvs_p"],
            "consequence": v["consequence"], "gnomad_af": v["gnomad_af"],
            "showcase": v["showcase"], "showcase_label": v["showcase_label"],
            "condition": v["condition"],
        }
        for v in ALL_VARIANTS
    ]


@app.get("/api/variants/{variant_id}")
def get_variant(variant_id: str) -> dict[str, Any]:
    v = VARIANTS_BY_ID.get(variant_id)
    if not v:
        raise HTTPException(404, "Variant not found")
    return {k: val for k, val in v.items() if k != "_target_hint"}

# ---------------------------------------------------------------------------
# Analysis pipeline (Problem 62 core)
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    variant_id: str
    patient_id: str | None = None


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest) -> dict[str, Any]:
    v = VARIANTS_BY_ID.get(req.variant_id)
    if not v:
        raise HTTPException(404, "Variant not found")

    esm = esm_representation(v)
    ml = predict(v, esm["delta_score"])
    acmg = classify(v)

    ml_bucket = _bucket(ml["top_class"])
    acmg_bucket = _bucket(acmg["classification"])
    concordant = ml_bucket == acmg_bucket
    reconciliation = {
        "status": "CONCORDANT" if concordant else "DISCORDANT",
        "confidence": "HIGH CONFIDENCE" if concordant else "HUMAN REVIEW REQUIRED",
        "ml_bucket": ml_bucket,
        "acmg_bucket": acmg_bucket,
        # The final classification is ALWAYS the ACMG rule-engine output.
        "final_classification": acmg["classification"],
        "authority": "ACMG/AMP rule engine (ML never overrides deterministic evidence)",
        "note": (
            "AI prediction and ACMG evidence agree — interpretation recorded with high confidence."
            if concordant else
            f"AI predicts {ml['top_class']} but ACMG evidence supports {acmg['classification']}. "
            "The system defers to ACMG and flags this variant for expert human review."
        ),
    }

    patient_id = req.patient_id or "UNASSIGNED"
    block = provenance.record_interpretation(
        patient_id, v["id"], f"{v['gene']} {v['hgvs_c']}", acmg["classification"],
        reconciliation["status"], acmg["met_criteria"], ml["top_class"],
    )

    return {
        "variant": {k: val for k, val in v.items() if k != "_target_hint"},
        "esm2": esm,
        "ml": ml,
        "acmg": acmg,
        "reconciliation": reconciliation,
        "provenance": {
            "recorded": True,
            "contract": CONTRACT_INTERPRETATION,
            "tx_id": block["tx_id"],
            "block_index": block["block_index"],
            "interpretation_hash": block["payload"]["interpretation_hash"],
            "patient_hash": block["payload"]["patient_hash"],
            "model_version": MODEL_VERSION,
            "evidence_version": EVIDENCE_VERSION,
            "timestamp": block["timestamp"],
        },
        "mode": "DEMO_MODE" if DEMO_MODE else "LIVE_MODE",
    }

# ---------------------------------------------------------------------------
# Patients & clinical context (Problem 60 downstream layer)
# ---------------------------------------------------------------------------

@app.get("/api/patients")
def list_patients() -> list[dict[str, Any]]:
    return PATIENTS


@app.get("/api/patients/{patient_id}")
def get_patient(patient_id: str) -> dict[str, Any]:
    p = PATIENTS_BY_ID.get(patient_id)
    if not p:
        raise HTTPException(404, "Patient not found")
    return p


@app.get("/api/patients/{patient_id}/context")
def patient_context(patient_id: str) -> dict[str, Any]:
    p = PATIENTS_BY_ID.get(patient_id)
    if not p:
        raise HTTPException(404, "Patient not found")
    analyses = [analyze_variant_for_patient(p, vid) for vid in p["variant_ids"]]
    analyses.sort(key=lambda a: a["relevance"]["score"], reverse=True)
    return {"patient": p, "analyses": analyses}

# ---------------------------------------------------------------------------
# Knowledge graph
# ---------------------------------------------------------------------------

@app.get("/api/graph/{patient_id}")
def knowledge_graph(patient_id: str) -> dict[str, Any]:
    p = PATIENTS_BY_ID.get(patient_id)
    if not p:
        raise HTTPException(404, "Patient not found")
    return build_knowledge_graph(p)

# ---------------------------------------------------------------------------
# Provenance / contract functions
# ---------------------------------------------------------------------------

class TxRequest(BaseModel):
    tx_id: str


class ConsentRequest(BaseModel):
    patient_id: str
    scope: str | None = None


@app.get("/api/provenance/audit")
def audit_trail(patient_id: str | None = None) -> dict[str, Any]:
    return {
        "blocks": provenance.get_audit_trail(patient_id),
        "stats": provenance.ledger_stats(),
        "contracts": [CONTRACT_CONSENT, CONTRACT_INTERPRETATION],
        "contract_functions": [
            "recordConsent()", "verifyConsent()", "revokeConsent()",
            "recordInterpretation()", "verifyInterpretation()", "getAuditTrail()",
        ],
    }


@app.post("/api/provenance/verify")
def verify_tx(req: TxRequest) -> dict[str, Any]:
    return provenance.verify_interpretation(req.tx_id)


@app.get("/api/provenance/consent/{patient_id}")
def consent_state(patient_id: str) -> dict[str, Any]:
    return provenance.verify_consent(patient_id)


@app.post("/api/provenance/consent/record")
def consent_record(req: ConsentRequest) -> dict[str, Any]:
    p = PATIENTS_BY_ID.get(req.patient_id)
    scope = req.scope or (p["consent_scope"] if p else "Diagnostic germline analysis")
    return provenance.record_consent(req.patient_id, scope)


@app.post("/api/provenance/consent/revoke")
def consent_revoke(req: ConsentRequest) -> dict[str, Any]:
    return provenance.revoke_consent(req.patient_id)
