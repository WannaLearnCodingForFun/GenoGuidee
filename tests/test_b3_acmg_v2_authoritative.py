"""
Phase B3 — confirms (rather than assumes) that the authenticated research
path (POST /api/v1/interpret, now gated by a real Supabase identity per
Phase B1) runs ACMG v2 as the sole classification authority, and that the
legacy /api/analyze demo path (ACMG v1 + demo XGBoost) is untouched and
distinct.
"""
from __future__ import annotations

import random

from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def test_authenticated_interpret_runs_acmg_v2_not_v1(supabase_auth_as):
    from app.interpretation.acmg_v2 import ENGINE_VERSION

    with _client() as client:
        r = client.post(
            "/api/v1/interpret",
            json={"variant": {"chromosome": "17", "position": 43057062,
                              "reference": "T", "alternate": "TG"}},
            headers=supabase_auth_as("doctor"),
        )
        assert r.status_code == 200
        body = r.json()
        # ACMG v2 evaluator output — v1 (app/acmg.py) has no such field.
        assert "acmg_interpretation" in body
        assert body["acmg_interpretation"]["rule_version"]
        assert ENGINE_VERSION  # sanity: v2 module imports and is versioned


def test_reconciliation_final_classification_is_always_acmg(supabase_auth_as):
    """No code path may let anything (ML, a future classifier, therapy
    ranking) override ACMG v2's own classification."""
    with _client() as client:
        for _ in range(5):
            r = client.post(
                "/api/v1/interpret",
                json={"variant": {"chromosome": "17", "position": 43057062,
                                  "reference": "T", "alternate": "TG"}},
                headers=supabase_auth_as("doctor"),
            )
            assert r.status_code == 200
            body = r.json()
            assert body["reconciliation"]["final_classification"] == body["acmg_interpretation"]["classification"]


def test_legacy_demo_path_uses_acmg_v1_and_is_untouched():
    """Confirms by reading the actual response shape, not by assumption:
    /api/analyze has no acmg_interpretation/rule_version — it's the frozen
    v1 + demo-XGBoost path and must stay that way."""
    with _client() as client:
        r = client.post("/api/analyze", json={"variant_id": "VAR-BRCA1-5266DUP", "patient_id": "G-1027"})
        assert r.status_code == 200
        body = r.json()
        assert "acmg_interpretation" not in body
        assert "acmg" in body  # v1's flat shape (see app/acmg.py:classify)
        assert body["reconciliation"]["final_classification"] == body["acmg"]["classification"]
