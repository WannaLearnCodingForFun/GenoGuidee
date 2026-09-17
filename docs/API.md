# Clinical API

Base: `http://localhost:8000` (Bearer `genoguide_token` or Supabase JWT)

## Auth

- `POST /api/auth/signup` `{email,password,full_name,role}`
- `POST /api/auth/login`
- `GET /api/auth/me`

## Patients

- `GET /api/clinical/patients` — RBAC-filtered (lab sees all)
- `GET /api/clinical/patients/{id}` — bundle
- `POST /api/clinical/workup` — doctor only; requires an existing `patient_identifier` from patient signup
- `GET /api/clinical/patient-lookup?identifier=` — doctor/lab confirm a registered Patient ID
- `GET /api/clinical/patients/{id}/graph`
- `GET /api/clinical/patients/{id}/provenance`
- `GET /api/clinical/patients/{id}/consent`
- `GET /api/clinical/patients/{id}/audit`
- `GET /api/clinical/patients/{id}/candidates` — ClinVar/HPO candidates
- `GET /api/clinical/patients/{id}/longitudinal` — observed VAF points (legacy)
- `GET /api/clinical/patients/{id}/genomics/timeline`
- `GET /api/clinical/patients/{id}/genomics/snapshots`
- `GET /api/clinical/patients/{id}/genomics/snapshots/{sid}`
- `GET /api/clinical/patients/{id}/genomics/variants`
- `GET /api/clinical/patients/{id}/genomics/variants/{canonical_id}/trajectory`
- `GET /api/clinical/patients/{id}/genomics/summary`
- `GET /api/clinical/patients/{id}/genomics/projection`
- `GET /api/clinical/patients/{id}/genomics/therapy-relevance`
- `GET /api/clinical/patients/{id}/report-revisions`
- `POST /api/clinical/demo/longitudinal` — doctor/lab synthetic fixture
- `GET /api/clinical/models/evaluation` — doctor/lab registry metrics
- `GET|PATCH /api/clinical/patients/{id}/report` — PATCH is lab technician only

## Files / variants

- `POST /api/clinical/uploads` — patient role auto-binds session patient
- `GET /api/clinical/uploads` / `{id}`
- `POST /api/clinical/uploads/{id}/assign`
- `GET /api/clinical/variants`
- `POST /api/clinical/variants/{id}/interpret`
- `GET /api/clinical/curated?gene=`
- `POST /api/clinical/curated/interpret`

## Health

- `GET /health` and `GET /api/system/health`
- Components: backend, acmg, ml, therapy, database, provenance, datasets, vcf_parser, knowledge_graph, ngrok

Therapy `READY` for local Medical_DrugRecommendation when enabled; remote ngrok is probed separately and is `DEGRADED` if the health check fails.

## Platform `/api/v1` (additive; feature-flagged)

Existing v1 paths above are unchanged. New routes (OpenAPI: `/docs`):

| Method | Path | Flag |
|---|---|---|
| POST | `/api/v1/evidence/graph/edge` | ENABLE_EVIDENCE_GRAPH |
| GET | `/api/v1/graph?seed=` | ENABLE_EVIDENCE_GRAPH |
| POST | `/api/v1/evidence/radar` | ENABLE_EVIDENCE_GRAPH |
| POST | `/api/v1/evidence/explain` | ENABLE_EXPLANATION |
| GET | `/api/v1/evidence/timeline/{variant_id}` | ENABLE_EVIDENCE_TIMELINE |
| GET | `/api/v1/interpretations/{id}/history` | ENABLE_INTERPRETATION_VERSIONING |
| GET | `/api/v1/interpretations/{id}/diff/{a}/{b}` | ENABLE_INTERPRETATION_VERSIONING |
| POST | `/api/v1/reanalysis/check` `/run` | ENABLE_REANALYSIS |
| GET | `/api/v1/reanalysis/jobs/{id}` `/changes` | ENABLE_REANALYSIS |
| POST/GET | `/api/v1/watchlist` | ENABLE_WATCHLIST |
| POST | `/api/v1/phenotypes/normalize` `/match` `/rank-genes` `/rank-diseases` | ENABLE_PHENOTYPE_ENGINE |
| POST | `/api/v1/phenotypes/evolution` | ENABLE_PHENOTYPE_ENGINE |
| POST | `/api/v1/inheritance/solve` | ENABLE_INHERITANCE_SOLVER |
| POST | `/api/v1/acmg/simulate` | ENABLE_VARIANT_SIMULATOR |
| POST | `/api/v1/curation` | ENABLE_HUMAN_REVIEW |
| POST | `/api/v1/phenopackets/import` | ENABLE_PHENOPACKET |
| GET | `/api/v1/cases/{id}/phenopacket` | ENABLE_PHENOPACKET |
| POST/GET | `/api/v1/cohorts*` | ENABLE_COHORT_MODE (default **false**) |
| POST/GET | `/api/v1/model-monitoring*` | ENABLE_MODEL_MONITORING |

Structured errors on these routes:

```json
{"error": {"code": "FEATURE_DISABLED", "message": "...", "request_id": "..."}}
```

Legacy FastAPI `{"detail": ...}` responses are unchanged.

