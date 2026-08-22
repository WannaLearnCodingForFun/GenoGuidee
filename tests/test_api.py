from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def test_v1_health():
    with _client() as client:
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_v1_acmg_evaluate_empty():
    with _client() as client:
        r = client.post("/api/v1/acmg/evaluate", json={})
        assert r.status_code == 200
        body = r.json()
        assert body["classification"] == "VUS"
        assert body["met_criteria"] == []


def test_legacy_status_still_works():
    with _client() as client:
        r = client.get("/api/status")
        assert r.status_code == 200
        names = [c["name"] for c in r.json()["components"]]
        assert "ACMG Engine" in names


def test_role_forbidden():
    with _client() as client:
        r = client.post("/api/v1/interpret",
                        json={"variant": {"chromosome": "17", "position": 1,
                                          "reference": "A", "alternate": "T"}},
                        headers={"X-Role": "PATIENT"})
        assert r.status_code == 403


def test_normalize_variant():
    with _client() as client:
        r = client.post("/api/v1/variants/normalize",
                        json={"chromosome": "chr17", "position": 43057062,
                              "reference": "T", "alternate": "TG"})
        assert r.status_code == 200
        assert r.json()["variant_id"].startswith("GRCh38:17:")


def test_legacy_analyze_shape_unchanged():
    """Frontend contract: /api/analyze must not grow required fields."""
    with _client() as client:
        r = client.post("/api/analyze",
                        json={"variant_id": "VAR-BRCA1-5266DUP", "patient_id": "G-1027"})
        assert r.status_code == 200
        body = r.json()
        for key in ("variant", "esm2", "ml", "acmg", "reconciliation", "provenance", "mode"):
            assert key in body
        assert "somatic_therapy" not in body


def test_therapy_status_offline_by_default():
    with _client() as client:
        r = client.get("/api/v1/therapy/status")
        assert r.status_code == 200
        assert r.json()["enabled"] is False


def test_therapy_map_endpoint():
    with _client() as client:
        r = client.get("/api/v1/therapy/map",
                       params={"hgvs_p": "p.Leu858Arg", "disease": "lung adenocarcinoma"})
        assert r.status_code == 200
        assert r.json()["protein_shorthand"] == "L858R"
        assert r.json()["indication"] == "NSCLC"


def test_therapy_recommend_disabled_still_200():
    with _client() as client:
        r = client.post("/api/v1/therapy/recommend",
                        json={"gene": "EGFR", "variant": "L858R", "disease": "NSCLC"})
        assert r.status_code == 200
        assert r.json()["availability"] == "SOURCE_NOT_CONFIGURED"


def test_patient_cannot_call_therapy_recommend():
    with _client() as client:
        r = client.post("/api/v1/therapy/recommend",
                        json={"gene": "EGFR", "variant": "L858R", "disease": "NSCLC"},
                        headers={"X-Role": "PATIENT"})
        assert r.status_code == 403


def test_frontend_health():
    with _client() as client:
        r = client.get("/api/v1/frontend/health")
        assert r.status_code == 200
        assert r.json()["layer"] == "frontend-bridge"
        assert r.json()["ok"] is True


def test_frontend_therapy_normalizes_and_stays_200_when_offline():
    with _client() as client:
        r = client.post("/api/v1/frontend/therapy", json={
            "mutation": {"gene": "EGFR", "protein_change": "p.Leu858Arg"},
            "clinical": {"indication": "lung adenocarcinoma"},
        })
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["normalized"] == {"gene": "EGFR", "variant": "L858R", "disease": "NSCLC"}
        assert body["recommendation"]["availability"] == "SOURCE_NOT_CONFIGURED"


def test_frontend_therapy_rejects_phi():
    with _client() as client:
        r = client.post("/api/v1/frontend/therapy", json={
            "mutation": {"gene": "EGFR", "variant": "L858R"},
            "clinical": {"disease": "NSCLC"},
            "patient_id": "G-1027",
        })
        assert r.status_code == 400


def test_frontend_therapy_unmappable_is_422():
    with _client() as client:
        r = client.post("/api/v1/frontend/therapy", json={
            "mutation": {"gene": "EGFR", "protein_change": "c.2573T>G"},
            "clinical": {"disease": "NSCLC"},
        })
        assert r.status_code == 422


def test_frontend_therapy_tunnel_key_required(monkeypatch):
    monkeypatch.setenv("GENOGUIDE_TUNNEL_KEY", "secret-demo")
    with _client() as client:
        denied = client.post("/api/v1/frontend/therapy", json={
            "mutation": {"gene": "EGFR", "variant": "L858R"},
            "clinical": {"disease": "NSCLC"},
        })
        assert denied.status_code == 401
        ok = client.post("/api/v1/frontend/therapy",
                         json={"mutation": {"gene": "EGFR", "variant": "L858R"},
                               "clinical": {"disease": "NSCLC"}},
                         headers={"X-GenoGuide-Key": "secret-demo"})
        assert ok.status_code == 200


def test_frontend_therapy_patient_role_blocked_without_key():
    with _client() as client:
        r = client.post("/api/v1/frontend/therapy",
                        json={"gene": "EGFR", "variant": "L858R", "disease": "NSCLC"},
                        headers={"X-Role": "PATIENT"})
        assert r.status_code == 403


def test_interpret_germline_marks_therapy_not_applicable():
    with _client() as client:
        r = client.post("/api/v1/interpret",
                        json={"variant": {"chromosome": "17", "position": 1,
                                          "reference": "A", "alternate": "T"}},
                        headers={"X-Role": "DOCTOR"})
        assert r.status_code == 200
        body = r.json()
        assert body["somatic_therapy"]["availability"] == "NOT_APPLICABLE"
        assert body["reconciliation"]["final_classification"] == body["acmg_interpretation"]["classification"]
