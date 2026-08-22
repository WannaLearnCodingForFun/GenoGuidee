"""FastAPI endpoints for drug recommendation module.

Exposes POST /drug-recommendation and POST /api/drug-recommendation.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# Ensure package root on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from recommendation.recommender import recommend_drugs


class DrugRecommendationRequest(BaseModel):
    gene: str = Field(..., example="EGFR", description="Target gene symbol")
    variant: str = Field(..., example="L858R", description="Genomic or amino acid variant")
    disease: str = Field(..., example="NSCLC", description="Disease or cancer context")


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


router = APIRouter(tags=["Drug Recommendation"])


@router.post(
    "/drug-recommendation",
    response_model=DrugRecommendationResponse,
    summary="Get ranked therapeutic drug recommendations for a genomic variant",
)
@router.post(
    "/api/drug-recommendation",
    response_model=DrugRecommendationResponse,
    summary="Get ranked therapeutic drug recommendations for a genomic variant",
)
def get_drug_recommendations(req: DrugRecommendationRequest) -> DrugRecommendationResponse:
    """Accepts gene, variant, and disease, returning ranked drug recommendations."""
    if not req.gene or not req.variant or not req.disease:
        raise HTTPException(status_code=400, detail="gene, variant, and disease fields are required.")

    payload = {
        "gene": req.gene,
        "variant": req.variant,
        "disease": req.disease,
    }

    try:
        res = recommend_drugs(payload)
        return DrugRecommendationResponse(**res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Drug recommendation calculation error: {str(e)}")
