"""Security: patient isolation, researcher de-identification, unauthorized finalize."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GENOGUIDE_CLINICAL_DB", str(tmp_path / "clinical.db"))
    monkeypatch.setenv("GENOGUIDE_SECRET_KEY", "test-secret")
    monkeypatch.setenv("ENABLE_COHORT_MODE", "true")
    from app.main import app
    with TestClient(app) as c:
        yield c


def _signup(client: TestClient, email: str, role: str):
    r = client.post("/api/auth/signup", json={
        "email": email, "password": "secret12", "full_name": email.split("@")[0], "role": role,
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_patient_cannot_access_another_patient_watchlist(client):
    a = _signup(client, "a@ex.com", "patient")
    b = _signup(client, "b@ex.com", "patient")
    token_a = a["token"]
    pid_b = b["patient"]["id"]
    r = client.get(f"/api/v1/watchlist?patient_id={pid_b}",
                   headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


def test_unauthorized_user_cannot_finalize(client):
    from app.platform import interpretations as I
    I.record(
        interpretation_id="INT-SEC", classification="VUS",
        acmg_criteria={}, ml_prediction={}, model_version="m",
        phenotype_score=None, evidence_ids=[], kg_version="k", guideline_version="g",
    )
    # request_review first so finalize from AI_DRAFT is invalid anyway; patient still 403
    r = client.post("/api/v1/curation", json={
        "interpretation_id": "INT-SEC", "action": "finalize", "reason": "nope",
    }, headers={"X-Role": "PATIENT"})
    assert r.status_code == 403
    assert "cannot finalize" in r.json()["error"]["message"]


def test_researcher_bundle_has_no_identity(client):
    created = client.post("/api/v1/cohorts", json={"name": "sec"})
    cid = created.json()["cohort_id"]
    client.post(f"/api/v1/cohorts/{cid}/cases", json={"case_id": "C1", "patient_id": 99})
    body = client.get(f"/api/v1/cohorts/{cid}", headers={"X-Role": "RESEARCHER"}).json()
    joined = str(body)
    assert "full_name" not in joined
    assert "@" not in joined
    assert body["identity_fields_present"] is False
