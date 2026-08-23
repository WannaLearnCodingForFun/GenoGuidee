"""GenoGuide backend — FastAPI application."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import provenance, uploads, workup
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
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("genoguide")
    log.info("[BACKEND] starting FastAPI on local process")
    from . import clinical_db as clinical_db
    clinical_db.init()
    log.info("[DATABASE] clinical SQLite ready")
    provenance.init_ledger()
    log.info("[PROVENANCE] local hash-chain ledger initialized (not Hyperledger Fabric)")
    try:
        init_xgboost()
        if xgb_status().get("ready"):
            log.info("[ML] demo XGBoost artifact present (not used as clinical application state)")
        else:
            log.warning("[ML] demo XGBoost not ready")
    except Exception as exc:  # noqa: BLE001 — demo ML must not block the API
        log.warning("[ML] demo XGBoost not started: %s", exc)
    log.info("[ACMG] deterministic engine mounted (authoritative; ML never overrides)")
    yield
    log.info("[BACKEND] shutting down")


app = FastAPI(title="GenoGuide API", version="1.0.0", lifespan=lifespan)

# Local Next.js + optional tunneled / hosted frontends. ngrok-free hostnames
# change every session — regex covers the public HTTPS hop without listing each URL.
_CORS_EXTRA = [o.strip().rstrip("/") for o in os.environ.get("GENOGUIDE_CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", *_CORS_EXTRA],
    allow_origin_regex=(
        r"https://[a-z0-9-]+\.(ngrok-free\.dev|ngrok-free\.app|ngrok\.app|ngrok\.io)"
    ),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Research-engine API v1 (legacy /api/* endpoints above/below are preserved
# unchanged for the existing frontend). Optional: v1 requires the research
# data stores; if unavailable the router still mounts and reports states.
try:
    from .api.v1 import router as v1_router
    app.include_router(v1_router)
    logging.getLogger("genoguide").info("[RESEARCH] /api/v1 mounted")
except Exception as _v1_err:  # noqa: BLE001 — legacy demo API must keep working
    logging.getLogger("genoguide").warning("[RESEARCH] API v1 unavailable: %s", _v1_err)

try:
    from .clinical_routes import router as clinical_router
    app.include_router(clinical_router)
    logging.getLogger("genoguide").info("[CLINICAL] auth/workup/upload routes mounted")
except Exception as _clin_err:  # noqa: BLE001
    logging.getLogger("genoguide").warning("[CLINICAL] routes unavailable: %s", _clin_err)

# ---------------------------------------------------------------------------
# Drug Recommendation Module Router Integration
# ---------------------------------------------------------------------------
import sys
from pathlib import Path
_med_dir = Path(__file__).resolve().parent.parent.parent / "Medical_DrugRecommendation"
if str(_med_dir) not in sys.path:
    sys.path.insert(0, str(_med_dir))

try:
    from .services.drug_recommendation import _sklearn_pickle_compat
    _sklearn_pickle_compat()
except Exception:
    pass

try:
    from api.routes import router as drug_rec_router
    app.include_router(drug_rec_router)
except Exception as _e:
    print(f"Notice: Drug recommendation router load error: {_e}")


# ---------------------------------------------------------------------------
# System status / overview
# ---------------------------------------------------------------------------

@app.get("/health")
def root_health() -> dict[str, Any]:
    from .health import assemble_health
    return assemble_health()


@app.get("/health/detailed")
def root_health_detailed() -> dict[str, Any]:
    from .health import assemble_health
    return assemble_health(detailed=True)


@app.get("/api/health")
def api_health() -> dict[str, Any]:
    from .health import assemble_health
    return assemble_health()


@app.get("/api/status")
def status() -> dict[str, Any]:
    ledger = provenance.ledger_stats()
    esm = esm_status()
    return {
        "mode": "DEMO_MODE" if DEMO_MODE else "LIVE_MODE",
        "components": [
            {"name": "ESM-2", "ready": bool(esm.get("ready")), "detail": esm},
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


def _reconcile(ml: dict[str, Any], acmg: dict[str, Any]) -> dict[str, Any]:
    """Shared governance rule: ACMG is always the authority, ML is advisory."""
    ml_bucket = _bucket(ml["top_class"])
    acmg_bucket = _bucket(acmg["classification"])
    concordant = ml_bucket == acmg_bucket
    return {
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


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest) -> dict[str, Any]:
    v = VARIANTS_BY_ID.get(req.variant_id)
    if not v:
        raise HTTPException(404, "Variant not found")

    esm = esm_representation(v)
    ml = predict(v, esm["delta_score"])
    acmg = classify(v)
    reconciliation = _reconcile(ml, acmg)

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
# Uploaded-VCF analysis
#
# The curated dataset lives in memory here; uploaded variants live in Supabase
# under row-level security. So this endpoint is stateless with respect to
# storage: the client sends the parsed annotations it is authorized to read,
# and gets back the identical ACMG -> ML -> reconciliation -> provenance
# treatment the curated variants receive.
# ---------------------------------------------------------------------------

class UploadedVariantRequest(BaseModel):
    chrom: str
    pos: int
    ref: str
    alt: str
    gene: str | None = None
    transcript: str | None = None
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    consequence: str | None = None
    gnomad_af: float | None = None
    cadd: float | None = None
    revel: float | None = None
    spliceai: float | None = None
    phylop: float | None = None
    # Opaque references used for the provenance record. No genomic or clinical
    # content — the ledger only ever stores hashes of these.
    subject_ref: str | None = None
    upload_id: str | None = None


@app.post("/api/analyze/uploaded")
def analyze_uploaded(req: UploadedVariantRequest) -> dict[str, Any]:
    v = uploads.normalize(req.model_dump())

    esm = esm_representation(v)
    if esm["mode"] == "demo-precomputed":
        # Make it explicit that the delta is derived from the file's own
        # annotations rather than curated or produced by a live ESM-2 run.
        esm = {**esm, "mode": "proxy-from-annotations"}
    ml = predict(v, esm["delta_score"])
    acmg = classify(v)
    reconciliation = _reconcile(ml, acmg)

    subject = req.subject_ref or "UPLOAD-UNASSIGNED"
    block = provenance.record_interpretation(
        subject, v["id"], f"{v['gene']} {v['hgvs_c']}", acmg["classification"],
        reconciliation["status"], acmg["met_criteria"], ml["top_class"],
    )

    return {
        "variant": {k: val for k, val in v.items() if k not in ("missing_evidence", "annotation_completeness")},
        "esm2": esm,
        "ml": ml,
        "acmg": acmg,
        "reconciliation": reconciliation,
        "annotation_completeness": v["annotation_completeness"],
        "missing_evidence": v["missing_evidence"],
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
        "source": "upload",
    }

# ---------------------------------------------------------------------------
# Clinical workup — the full staged flow
#
#   intake (history + variant) -> triple (gene/variant/disease)
#   -> classification (ACMG || ML) -> reconciliation -> medication
#
# Each stage is returned separately so the UI can reveal them in order and
# show exactly where a run stopped and why.
# ---------------------------------------------------------------------------

class HistoryPayload(BaseModel):
    age: int | None = None
    sex: str | None = None
    diagnosis: str | None = None
    presenting_complaint: str | None = None
    phenotypes: list[str] = []
    prior_conditions: list[str] = []
    medications: list[str] = []
    family_history_positive: bool = False
    family_details: str | None = None
    consent_confirmed: bool = False


class WorkupRequest(BaseModel):
    # Exactly one variant source: a curated dataset id, or an inline record
    # parsed from an uploaded VCF.
    variant_id: str | None = None
    uploaded_variant: UploadedVariantRequest | None = None
    history: HistoryPayload = HistoryPayload()
    subject_ref: str | None = None


@app.post("/api/workup")
def clinical_workup(req: WorkupRequest) -> dict[str, Any]:
    # --- stage 1: intake -------------------------------------------------
    if req.variant_id:
        variant = VARIANTS_BY_ID.get(req.variant_id)
        if not variant:
            raise HTTPException(404, "Variant not found")
        variant_source = "curated"
        missing_evidence: list[dict[str, str]] = []
        completeness = None
    elif req.uploaded_variant:
        variant = uploads.normalize(req.uploaded_variant.model_dump())
        variant_source = "upload"
        missing_evidence = variant["missing_evidence"]
        completeness = variant["annotation_completeness"]
    else:
        raise HTTPException(422, "Provide either variant_id or uploaded_variant")

    history = req.history.model_dump()
    summary = workup.summarize_history(history)

    # --- stage 2: gene / variant / disease --------------------------------
    triple = workup.resolve_triple(variant, history)

    # --- stage 3: independent classification paths ------------------------
    esm = esm_representation(variant)
    if variant_source == "upload" and esm["mode"] == "demo-precomputed":
        esm = {**esm, "mode": "proxy-from-annotations"}
    ml = predict(variant, esm["delta_score"])
    acmg = classify(variant)

    # --- stage 4: reconciliation ------------------------------------------
    reconciliation = _reconcile(ml, acmg)
    final_classification = reconciliation["final_classification"]
    human_review_required = reconciliation["status"] == "DISCORDANT"

    overlap = workup.phenotype_overlap(triple["gene"], summary)

    # --- stage 5: medication (gated on the verdict above) ------------------
    medication = workup.medication_stage(
        triple, final_classification, reconciliation["status"], human_review_required,
    )

    considerations = workup.history_considerations(
        summary, overlap, triple, final_classification, history,
    )

    # Seal the interpretation. Only hashes reach the ledger.
    block = provenance.record_interpretation(
        req.subject_ref or "WORKUP-UNASSIGNED", variant["id"],
        f"{variant['gene']} {variant['hgvs_c']}", acmg["classification"],
        reconciliation["status"], acmg["met_criteria"], ml["top_class"],
    )

    return {
        "stages": [
            {"id": "intake", "label": "Intake", "status": "COMPLETE"},
            {"id": "triple", "label": "Gene · Variant · Disease",
             "status": "COMPLETE" if triple["complete"] else "PARTIAL"},
            {"id": "classification", "label": "Classification", "status": "COMPLETE"},
            {"id": "reconciliation", "label": "AI vs ACMG", "status": reconciliation["status"]},
            {"id": "medication", "label": "Medication", "status": medication["availability"]},
        ],
        "variant": {k: v for k, v in variant.items()
                    if k not in ("_target_hint", "missing_evidence", "annotation_completeness")},
        "variant_source": variant_source,
        "annotation_completeness": completeness,
        "missing_evidence": missing_evidence,
        "history_summary": summary,
        "triple": triple,
        "esm2": esm,
        "ml": ml,
        "acmg": acmg,
        "reconciliation": reconciliation,
        "phenotype_overlap": overlap,
        "medication": medication,
        "considerations": considerations,
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
    """Persisted clinical patients only — never the synthetic G-1027 cohort."""
    from . import clinical_db as C
    C.init()
    return []


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
