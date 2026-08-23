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
- `GET /api/clinical/patients/{id}/longitudinal`
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
