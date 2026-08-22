"""
Supabase identity bridge (Phase B1).

Verifies a Supabase-issued access token by asking Supabase's own GoTrue
endpoint (`/auth/v1/user`) whether it's valid — this avoids ever needing the
project's JWT signing secret inside this service. Role is then looked up
server-side from `public.profiles` via the service-role key (never trusted
from the client). The legacy `X-Role` header (api/v1.py's `get_role`) keeps
its purely architectural role for internal/demo calls; endpoints that touch
real per-user patient data must depend on `require_supabase_user` instead,
which is the only source of authority for those routes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import httpx
from fastapi import Header, HTTPException

_TIMEOUT = 5.0

# Legacy X-Role -> Supabase role mapping used only by tests / internal
# tooling to keep the same fixtures readable; production callers must send
# a real bearer token. Read at call time (not module import time) so tests
# can monkeypatch os.environ.
def _supabase_url() -> str:
    return os.environ.get("SUPABASE_URL", "").rstrip("/")


def _supabase_anon_key() -> str:
    return os.environ.get("SUPABASE_ANON_KEY", "")


def _supabase_service_role_key() -> str:
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


@dataclass
class SupabaseUser:
    id: str
    email: Optional[str]
    role: str  # 'doctor' | 'patient' | 'lab_technician'


def _configured() -> bool:
    return bool(_supabase_url() and _supabase_anon_key() and _supabase_service_role_key())


def _extract_bearer(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(401, "missing bearer token")
    return token


def require_supabase_user(authorization: Optional[str] = Header(default=None)) -> SupabaseUser:
    """FastAPI dependency: 401s unless `Authorization: Bearer <supabase jwt>`
    is present and valid. Role comes from `profiles`, never from the client.
    """
    if not _configured():
        raise HTTPException(
            503,
            "Supabase identity bridge not configured "
            "(SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY missing)",
        )

    token = _extract_bearer(authorization)

    try:
        resp = httpx.get(
            f"{_supabase_url()}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": _supabase_anon_key()},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(503, f"identity provider unreachable: {exc}") from exc

    if resp.status_code != 200:
        raise HTTPException(401, "invalid or expired token")

    user = resp.json()
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(401, "invalid token payload")

    try:
        prof_resp = httpx.get(
            f"{_supabase_url()}/rest/v1/profiles",
            params={"id": f"eq.{user_id}", "select": "id,role"},
            headers={
                "Authorization": f"Bearer {_supabase_service_role_key()}",
                "apikey": _supabase_service_role_key(),
            },
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(503, f"profile lookup unreachable: {exc}") from exc

    if prof_resp.status_code != 200 or not prof_resp.json():
        raise HTTPException(401, "no profile for authenticated user")

    role = prof_resp.json()[0]["role"]
    return SupabaseUser(id=user_id, email=user.get("email"), role=role)


# Supabase role -> legacy X-Role-style permission bucket (api/v1.py's
# ROLE_PERMISSIONS). Accounts created via /signup never have a RESEARCHER /
# ADMIN / GENETIC_COUNSELOR role — those remain X-Role-hint-only for
# internal/research tooling, which does not touch a specific patient's data.
SUPABASE_ROLE_TO_PERMISSION_ROLE = {
    "doctor": "DOCTOR",
    "patient": "PATIENT",
    "lab_technician": "LAB_CLINICIAN",
}


def rest_get(path: str, params: dict) -> list[dict]:
    """Service-role read against the Supabase REST (PostgREST) API. Used for
    server-side lookups (e.g. interpretations.reviewed_by) that must not be
    trusted from the client. Returns [] if not configured/unreachable rather
    than raising, since callers treat an empty result as 'not found'."""
    if not _configured():
        return []
    try:
        resp = httpx.get(
            f"{_supabase_url()}/rest/v1/{path}",
            params=params,
            headers={
                "Authorization": f"Bearer {_supabase_service_role_key()}",
                "apikey": _supabase_service_role_key(),
            },
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError:
        return []
    if resp.status_code != 200:
        return []
    return resp.json()


def rest_insert(path: str, row: dict) -> bool:
    """Service-role write against PostgREST — used for server-side audit
    logging (Phase B7). Best-effort: never raises, since a logging failure
    must not break the request it's logging."""
    if not _configured():
        return False
    try:
        resp = httpx.post(
            f"{_supabase_url()}/rest/v1/{path}",
            json=row,
            headers={
                "Authorization": f"Bearer {_supabase_service_role_key()}",
                "apikey": _supabase_service_role_key(),
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError:
        return False
    return resp.status_code < 300


def log_audit(
    *,
    actor: "SupabaseUser",
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    detail: Optional[dict] = None,
) -> None:
    """Fire-and-forget audit log insert. Never raises — see rest_insert."""
    rest_insert(
        "audit_log",
        {
            "actor_id": actor.id,
            "actor_role": actor.role,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "patient_id": patient_id,
            "detail": detail or {},
        },
    )
