from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def test_root_health_has_component_states():
    with _client() as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in {"READY", "DEGRADED", "FAILED"}
        for name in ("backend", "acmg", "ml", "research", "therapy", "database", "provenance", "ngrok"):
            assert name in body["components"]
            assert body["components"][name]["status"] in {
                "READY", "DEGRADED", "OFFLINE", "NOT_CONFIGURED", "ERROR",
            }
        assert body["components"]["backend"]["status"] == "READY"
        assert body["components"]["acmg"]["status"] == "READY"
        assert body["components"]["ngrok"]["status"] == "NOT_CONFIGURED"


def test_detailed_health_is_honest_about_fabric():
    with _client() as client:
        r = client.get("/health/detailed")
        assert r.status_code == 200
        assert "fabric" in r.json()["notes"]
        assert "NOT IMPLEMENTED" in r.json()["notes"]["fabric"]


def test_api_health_alias():
    with _client() as client:
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["components"]["backend"]["status"] == "READY"
