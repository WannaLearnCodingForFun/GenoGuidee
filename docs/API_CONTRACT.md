# API contract (research engine ↔ future frontend)

Legacy demo routes under `/api/*` are **frozen** (see `backend/app/main.py`).
New clients must use `/api/v1`.

## Canonical interpretation object

`POST /api/v1/interpret` returns `InterpretationObject`
(`backend/app/schemas/interpretation.py`):

- `variant` — `CanonicalVariant` (explicit `genome_build`)
- `annotation` / `population_evidence` / `functional_evidence` / `sequence_model`
- `ml_prediction` (nullable)
- `acmg_interpretation` — full criterion list, never a bare string
- `reconciliation.final_classification` — **always ACMG**
- `phenotype_match` — context only
- `clinical_considerations[]` — advisory
- `uncertainty` / `human_review`
- `provenance` — hashes + versions, no genomic payload

Absence of a source is an explicit availability enum, never a zero.

## Auth

`X-Role` header is a **placeholder**. Roles: PATIENT, DOCTOR, LAB_CLINICIAN,
RESEARCHER, GENETIC_COUNSELOR, ADMIN. Replace before any network deployment.

## Identifiers

`patient_id`, `genomic_sample_id`, `case_id`, `interpretation_id` are distinct
concepts. The demo layer still uses synthetic patient IDs (G-1027, …).
