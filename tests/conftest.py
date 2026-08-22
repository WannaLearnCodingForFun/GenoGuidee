from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def mini_vcf() -> Path:
    return REPO / "tests/data/mini.vcf"


@pytest.fixture(autouse=True)
def _therapy_connector_offline_by_default(monkeypatch):
    """Pytest must not inherit a live/placeholder URL from the developer shell."""
    monkeypatch.delenv("GENOGUIDE_DRUG_API_ENABLED", raising=False)
    monkeypatch.delenv("GENOGUIDE_DRUG_API_URL", raising=False)
    monkeypatch.delenv("GENOGUIDE_DRUG_API_TIMEOUT", raising=False)
    monkeypatch.setenv("GENOGUIDE_DRUG_LOCAL", "false")


@pytest.fixture
def supabase_auth_as(monkeypatch):
    """Phase B1 test double: simulates a valid Supabase-issued bearer token
    for a given app_role ('doctor' | 'patient' | 'lab_technician'), without
    any live network call. Returns a function producing the Authorization
    header for `client.post(..., headers=supabase_auth_as('doctor'))`.

    Mocks the two httpx.get calls inside app.supabase_auth: GoTrue's
    /auth/v1/user (token -> user id) and PostgREST's /rest/v1/profiles
    (user id -> role) — the same two network hops the real dependency makes,
    just fed fixture data instead of hitting the live project.
    """
    import httpx

    from app import supabase_auth

    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    USERS = {
        "doctor": "11111111-1111-1111-1111-111111111111",
        "patient": "22222222-2222-2222-2222-222222222222",
        "lab_technician": "33333333-3333-3333-3333-333333333333",
    }

    def fake_get(url: str, *, headers=None, params=None, timeout=None):
        headers = headers or {}
        if url.endswith("/auth/v1/user"):
            token = headers.get("Authorization", "").removeprefix("Bearer ").strip()
            if token not in USERS.values():
                return httpx.Response(401, json={"error": "invalid token"})
            return httpx.Response(200, json={"id": token, "email": f"{token}@example.com"})
        if url.endswith("/rest/v1/profiles"):
            user_id = (params or {}).get("id", "").removeprefix("eq.")
            role = next((r for r, uid in USERS.items() if uid == user_id), None)
            if role is None:
                return httpx.Response(200, json=[])
            return httpx.Response(200, json=[{"id": user_id, "role": role}])
        if "/rest/v1/" in url:
            # Any other table (interpretations, etc.) — no live project in
            # tests, so lookups fail closed to "not found".
            return httpx.Response(200, json=[])
        raise AssertionError(f"unexpected URL in supabase_auth_as mock: {url}")

    monkeypatch.setattr(supabase_auth.httpx, "get", fake_get)

    def headers_for(role: str) -> dict:
        return {"Authorization": f"Bearer {USERS[role]}"}

    return headers_for
