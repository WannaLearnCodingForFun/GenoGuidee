from fastapi.testclient import TestClient


def test_v1_health():
    from app.main import app
    with TestClient(app) as client:
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_v1_acmg_evaluate_empty():
    from app.main import app
    with TestClient(app) as client:
        r = client.post("/api/v1/acmg/evaluate", json={})
        assert r.status_code == 200
        body = r.json()
        assert body["classification"] == "VUS"
        assert body["met_criteria"] == []


def test_legacy_status_still_works():
    from app.main import app
    with TestClient(app) as client:
        r = client.get("/api/status")
        assert r.status_code == 200
        names = [c["name"] for c in r.json()["components"]]
        assert "ACMG Engine" in names


def test_role_forbidden():
    from app.main import app
    with TestClient(app) as client:
        r = client.post("/api/v1/interpret",
                        json={"variant": {"chromosome": "17", "position": 1,
                                          "reference": "A", "alternate": "T"}},
                        headers={"X-Role": "PATIENT"})
        assert r.status_code == 403


def test_normalize_variant():
    from app.main import app
    with TestClient(app) as client:
        r = client.post("/api/v1/variants/normalize",
                        json={"chromosome": "chr17", "position": 43057062,
                              "reference": "T", "alternate": "TG"})
        assert r.status_code == 200
        assert r.json()["variant_id"].startswith("GRCh38:17:")
