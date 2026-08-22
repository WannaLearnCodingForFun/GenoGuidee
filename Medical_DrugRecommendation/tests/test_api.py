"""Integration tests for FastAPI recommendation endpoints and recommender pipeline."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from api.routes import router
from fastapi import FastAPI
from recommendation.recommender import recommend_drugs

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_recommender_pipeline_egfr() -> None:
    payload = {"gene": "EGFR", "variant": "L858R", "disease": "NSCLC"}
    res = recommend_drugs(payload)

    assert res["gene"] == "EGFR"
    assert res["variant"] == "L858R"
    assert res["disease"] == "NSCLC"
    assert "recommendations" in res
    assert len(res["recommendations"]) > 0

    top_rec = res["recommendations"][0]
    assert "drug" in top_rec
    assert "rank" in top_rec
    assert top_rec["rank"] == 1
    assert "score" in top_rec
    assert "response" in top_rec
    assert "evidence_level" in top_rec
    assert "evidence_count" in top_rec


def test_api_endpoint_post() -> None:
    response = client.post(
        "/drug-recommendation",
        json={"gene": "EGFR", "variant": "L858R", "disease": "NSCLC"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["gene"] == "EGFR"
    assert data["variant"] == "L858R"
    assert data["disease"] == "NSCLC"
    assert len(data["recommendations"]) > 0


def test_api_endpoint_alt_route() -> None:
    response = client.post(
        "/api/drug-recommendation",
        json={"gene": "BRAF", "variant": "V600E", "disease": "Melanoma"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["gene"] == "BRAF"
    assert data["variant"] == "V600E"
    assert data["disease"] == "Melanoma"
    assert len(data["recommendations"]) > 0
