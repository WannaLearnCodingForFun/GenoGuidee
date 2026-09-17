# Security

## Authentication

- Clinical app: local PBKDF2 + HMAC bearer (`GENOGUIDE_SECRET_KEY`) or optional Supabase JWT.
- Research `/api/v1/interpret` already requires a real token (not `X-Role` alone).
- Platform routes accept clinical bearer **or** `X-Role` for research-shaped APIs.
  `X-Role` remains an architecture hint — not production OIDC.

## RBAC

Clinical `users.role` CHECK stays `doctor | patient | lab_technician` (no table rebuild).
Platform maps those to DOCTOR / PATIENT / LAB_CLINICIAN. Extra roles
(GENETIC_COUNSELOR, RESEARCHER, ADMIN) are expressed via `X-Role` and
`user_platform_roles` — they are **not** smuggled into the CHECK constraint.

- PATIENT: own data only (`can_access_patient`).
- DOCTOR: assigned/created patients; may curate/finalize.
- LAB_CLINICIAN: laboratory cases; may finalize.
- RESEARCHER: de-identified cohort payloads only (`identity_fields_present: false`).
- Unauthorized finalize → `403 FORBIDDEN`.

## Secrets and logging

- Passwords: PBKDF2 only.
- Do not log raw genomic sequences or patient names in platform audit `object` fields;
  store IDs and structured before/after JSON.
- Never commit `.env` secrets. `GENOGUIDE_SECRET_KEY` must be set outside local demo.

## Errors

Platform routes return `{error: {code, message, request_id}}` and do not include stack traces.
Legacy routes keep FastAPI `detail` for compatibility.
