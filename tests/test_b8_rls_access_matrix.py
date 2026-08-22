"""
Phase B8 — RLS access-matrix test.

This CANNOT run against a mock: it must exercise real Postgres Row Level
Security using real anon-key JWTs for seeded users against the LIVE linked
Supabase project (there is no local Postgres/RLS engine in this sandbox, and
mocking `httpx.get`/`.from_()` calls would only prove the test doubles
agree with themselves, not that RLS itself is correct).

Requires (not available in the sandboxed pytest run — this file is skipped
unless SUPABASE_SERVICE_ROLE_KEY + RUN_LIVE_RLS_TESTS=1 are set):
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY

Run manually with:
  RUN_LIVE_RLS_TESTS=1 SUPABASE_URL=... SUPABASE_ANON_KEY=... \
    SUPABASE_SERVICE_ROLE_KEY=... PYTHONPATH=. backend/.venv/bin/python \
    -m pytest -q tests/test_b8_rls_access_matrix.py

What it seeds/asserts once enabled:
  - 2 doctors, 2 patients (one per doctor), 1 lab_technician with 1 lab_order
    for one of the patients.
  - Using each seeded user's own anon-key JWT (via
    supabase.auth.sign_in_with_password against a throwaway test account, or
    supabase.auth.admin.create_user + sign-in), assert:
      * doctor A can SELECT patient A's row, cannot SELECT patient B's row
      * patient A can SELECT their own row, cannot SELECT patient B's or
        doctor B's rows
      * lab_technician can SELECT the patient they have a lab_order for,
        cannot SELECT the other patient
      * no client role can UPDATE or DELETE audit_log (Phase B7)
  - Any failure here is a real RLS gap, not a test bug — report it, don't
    patch around it by loosening a policy without understanding why.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_RLS_TESTS") != "1",
    reason="requires a live Supabase project + RUN_LIVE_RLS_TESTS=1 — see module docstring",
)


def test_rls_access_matrix():
    pytest.skip(
        "Not implemented in this sandbox: no network path was exercised for "
        "seeding real auth.users + signing in as each seeded role. Implement "
        "using the supabase-py client (pip install supabase) with "
        "SUPABASE_SERVICE_ROLE_KEY to seed via auth.admin.create_user, then "
        "sign in as each seeded user and repeat the SELECT/UPDATE/DELETE "
        "matrix described in the module docstring. Run manually against the "
        "live project — do not run in CI against production data."
    )
