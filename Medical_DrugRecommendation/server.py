"""Production-ready FastAPI server for live deployment of the Drug Recommendation Model.

Runs locally on host PC with dataset pre-loading for sub-millisecond API response times,
CORS support, health monitoring, and OpenAPI docs.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
import sys
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Ensure module path is accessible
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from preprocessing.civic_parser import CIViCParser
from preprocessing.dgidb_parser import DGIdbParser
from recommendation.recommender import DrugRecommenderEngine


# Shared global engine instance pre-loaded at server startup
engine: DrugRecommenderEngine | None = None
startup_time: float = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load knowledge base datasets and ML model on startup for fast responses."""
    global engine, startup_time
    t0 = time.time()
    print("=================================================================")
    print("Launching GenoGuide Drug Recommendation FastAPI Production Server")
    print("=================================================================")
    print("Pre-loading CIViC and DGIdb knowledge base datasets into RAM...")

    civic = CIViCParser()
    civic.load_data()
    dgidb = DGIdbParser()
    dgidb.load_data()

    engine = DrugRecommenderEngine(civic_parser=civic, dgidb_parser=dgidb)
    # Warmup recommendation engine
    _ = engine.recommend({"gene": "EGFR", "variant": "L858R", "disease": "NSCLC"})

    startup_time = time.time()
    elapsed = startup_time - t0
    print(f"[READY] Knowledge Base & ML Model pre-loaded in {elapsed:.2f} seconds.")
    print("FastAPI Server Ready! Serving live endpoints at http://0.0.0.0:8000")
    print("=================================================================\n")
    yield
    print("Shutting down server...")


app = FastAPI(
    title="GenoGuide Precision Medicine Drug Recommendation API",
    description="Live FastAPI server for genomic variant drug recommendations using CIViC, DGIdb, and ML hybrid ranking.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for live web applications
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows requests from any frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request and Response Pydantic Models
class DrugRecommendationRequest(BaseModel):
    gene: str = Field(..., example="EGFR", description="Genomic gene symbol (e.g. EGFR, BRAF, KRAS)")
    variant: str = Field(..., example="L858R", description="Variant or protein change (e.g. L858R, V600E)")
    disease: str = Field(..., example="NSCLC", description="Cancer condition or disease context (e.g. NSCLC, Melanoma)")


class DrugRecommendationItem(BaseModel):
    drug: str
    rank: int
    score: float
    response: str
    evidence_level: str
    evidence_count: int


class DrugRecommendationResponse(BaseModel):
    gene: str
    variant: str
    disease: str
    recommendations: list[DrugRecommendationItem]


@app.get("/", summary="Root Status Endpoint")
def root_status() -> dict[str, Any]:
    """Server status overview."""
    return {
        "status": "online",
        "service": "GenoGuide Drug Recommendation Engine",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": ["/drug-recommendation", "/api/drug-recommendation", "/health"],
    }


@app.get("/health", summary="System Health & RAM Dataset Diagnostics")
def health_check() -> dict[str, Any]:
    """Health check endpoint detailing RAM dataset index counts."""
    if engine is None:
        return {"status": "unhealthy", "reason": "Engine not initialized"}

    civic_cnt = len(engine.civic_parser.evidence_items)
    dgidb_cnt = len(engine.dgidb_parser.interactions_by_gene)
    model_ready = engine.drug_ranker.model is not None

    return {
        "status": "healthy",
        "uptime_seconds": round(time.time() - startup_time, 2) if startup_time else 0,
        "datasets": {
            "civic_evidence_items_in_ram": civic_cnt,
            "dgidb_genes_indexed_in_ram": dgidb_cnt,
        },
        "ml_model": {
            "loaded": model_ready,
            "path": engine.drug_ranker.model_path,
        },
    }


@app.post(
    "/drug-recommendation",
    response_model=DrugRecommendationResponse,
    summary="Generate Ranked Therapeutic Drug Recommendations",
)
@app.post(
    "/api/drug-recommendation",
    response_model=DrugRecommendationResponse,
    summary="Generate Ranked Therapeutic Drug Recommendations",
)
def get_recommendations(req: DrugRecommendationRequest) -> DrugRecommendationResponse:
    """Core endpoint: Receives gene, variant, disease and returns ranked drug recommendations."""
    if engine is None:
        raise HTTPException(status_code=503, detail="Recommendation engine is initializing...")

    if not req.gene.strip() or not req.variant.strip() or not req.disease.strip():
        raise HTTPException(status_code=400, detail="Fields 'gene', 'variant', and 'disease' cannot be empty.")

    payload = {
        "gene": req.gene,
        "variant": req.variant,
        "disease": req.disease,
    }

    try:
        t_start = time.time()
        res = engine.recommend(payload)
        t_calc = (time.time() - t_start) * 1000.0
        # Print live request log to console
        print(f"[POST /drug-recommendation] {req.gene} {req.variant} ({req.disease}) -> Top 1: {res['recommendations'][0]['drug'] if res['recommendations'] else 'None'} ({t_calc:.1f} ms)")
        return DrugRecommendationResponse(**res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recommendation engine error: {str(e)}")


if __name__ == "__main__":
    # Launch production server listening on 0.0.0.0:8000
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False, workers=1)
