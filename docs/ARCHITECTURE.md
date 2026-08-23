# GenoGuide architecture

Decision-support prototype. Not a medical device. Predictions require human review.

```
AUTH → RBAC → SQLite clinical store → PATIENT → CLINICAL DATA
  → VARIANT SOURCE
       ├── CURATED_DATASET (ClinVar catalog; not confirmed in patient)
       └── UPLOADED_VCF / UPLOADED_TXT (patient observed)
  → annotation → ESM-2 (when torch+sequence exist) → XGBoost → calibration
  → ACMG (authoritative) → reconciliation → report
       ├── therapy evidence (local ranker and/or ngrok API)
       ├── patient-specific knowledge graph
       ├── hash-chained provenance
       └── longitudinal observations (real samples only)
```

## Stack

| Layer | Implementation |
|---|---|
| Frontend | Next.js App Router (`frontend/`) |
| Backend | FastAPI (`backend/app/main.py`) |
| Auth | Local PBKDF2 + bearer when Supabase env is unset; optional Supabase |
| Clinical DB | SQLite `backend/app/clinical.db` (override `GENOGUIDE_CLINICAL_DB`) |
| Legacy demo API | `/api/analyze` kept for existing tests; not the clinical source of truth |
| Clinical API | `/api/auth/*`, `/api/clinical/*` |

## Source of truth

The clinical SQLite database. Frontend state is a cache of API responses.
Interpretations are stored once and rendered as the same object in Variant Lab,
reports, and provenance.

## What is not implemented

- Time-to-death from a variant
- Invented VAF histories
- Fabricated therapy when no evidence exists
- Fake ESM-2 embeddings when the model is not loaded
