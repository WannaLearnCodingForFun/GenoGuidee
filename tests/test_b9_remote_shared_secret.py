"""Phase B9 — outbound calls to the further remote therapy engine attach the
shared secret; PHI never gets logged (there is no logging at all in these
modules, which trivially satisfies "never log the payload body")."""
from __future__ import annotations

from app.services import drug_recommendation as DR


def test_no_shared_secret_when_key_unset(monkeypatch):
    monkeypatch.delenv("GENOGUIDE_TUNNEL_KEY", raising=False)
    assert DR._remote_auth_headers() == {}


def test_shared_secret_attached_when_key_set(monkeypatch):
    monkeypatch.setenv("GENOGUIDE_TUNNEL_KEY", "secret-demo")
    assert DR._remote_auth_headers() == {"X-GenoGuide-Key": "secret-demo"}


def test_no_logging_calls_exist_in_therapy_modules():
    """Payload bodies can only leak via logging if a logging call exists at
    all — assert none do, in either the outbound (drug_recommendation) or
    inbound (frontend_bridge) side of the ngrok hop."""
    import inspect

    from app.services import frontend_bridge

    for mod in (DR, frontend_bridge):
        src = inspect.getsource(mod)
        assert "logging." not in src
        assert "logger." not in src
