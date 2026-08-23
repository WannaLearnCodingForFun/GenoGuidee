"""Therapy ranking: user input, normalization, and honest abstention."""
from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def test_protein_hgvs_normalizes_to_shorthand():
    from app.services.drug_recommendation import protein_shorthand
    assert protein_shorthand("p.Leu858Arg") == "L858R"
    assert protein_shorthand("L858R") == "L858R"
    assert protein_shorthand("GRCh38:7:55191822:T>G") is None
    assert protein_shorthand("c.2573T>G") is None


def test_frontend_bridge_normalizes_user_input():
    from app.services.frontend_bridge import normalize_frontend_payload
    out = normalize_frontend_payload({
        "mutation": {"gene": "EGFR", "protein_change": "p.Leu858Arg"},
        "clinical": {"indication": "NSCLC"},
    })
    assert out == {"gene": "EGFR", "variant": "L858R", "disease": "NSCLC"}


def test_unmappable_protein_is_422():
    with _client() as client:
        r = client.post("/api/v1/frontend/therapy", json={
            "mutation": {"gene": "EGFR", "protein_change": "c.2573T>G"},
            "clinical": {"indication": "NSCLC"},
        })
        assert r.status_code == 422
        assert "unmappable" in r.json()["detail"].lower()


def test_malformed_therapy_payload_is_422():
    with _client() as client:
        r = client.post("/api/v1/frontend/therapy", json={"mutation": {}, "clinical": {}})
        assert r.status_code == 422


def test_local_egfr_l858r_ranks(monkeypatch):
    monkeypatch.setenv("GENOGUIDE_DRUG_LOCAL", "true")
    monkeypatch.delenv("GENOGUIDE_DRUG_API_ENABLED", raising=False)
    monkeypatch.delenv("GENOGUIDE_DRUG_API_URL", raising=False)
    from app.services.drug_recommendation import recommend, reset_runtime_state
    reset_runtime_state()
    result = recommend("EGFR", "p.Leu858Arg", "NSCLC")
    assert result.abstained is False
    assert result.availability.value == "AVAILABLE"
    assert result.recommendations
    assert result.recommendations[0].drug


def test_unsupported_combination_abstains(monkeypatch):
    monkeypatch.setenv("GENOGUIDE_DRUG_LOCAL", "true")
    monkeypatch.delenv("GENOGUIDE_DRUG_API_ENABLED", raising=False)
    monkeypatch.delenv("GENOGUIDE_DRUG_API_URL", raising=False)
    from app.services.drug_recommendation import recommend, reset_runtime_state
    reset_runtime_state()
    result = recommend("FOO", "Z999Q", "UnknownCancer")
    assert result.abstained is True
    assert result.recommendations == []
    assert "coverage" in (result.reason or "").lower()


def test_frontend_therapy_abstains_outside_coverage(monkeypatch):
    monkeypatch.setenv("GENOGUIDE_DRUG_LOCAL", "true")
    monkeypatch.delenv("GENOGUIDE_DRUG_API_URL", raising=False)
    with _client() as client:
        r = client.post("/api/v1/frontend/therapy", json={
            "mutation": {"gene": "FOO", "protein_change": "Z999Q"},
            "clinical": {"indication": "UnknownCancer"},
        })
        assert r.status_code == 200
        rec = r.json()["recommendation"]
        assert rec["abstained"] is True
        assert rec["recommendations"] == []
