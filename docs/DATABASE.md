# Database

Single relational store: SQLite via `backend/app/clinical_db.py`.
Do not introduce a second application database.

Override path: `GENOGUIDE_CLINICAL_DB`.

## Core tables

- `users` — doctor / patient / lab_technician
- `patients` — `PAT-YYYY-NNNNNN` issued at patient signup; `user_id` is set then. Doctors attach; they do not insert a new identifier.
- `patient_assignments` — explicit extra access (doctors may also be assigned)
- `patient_phenotypes`, `family_history`, `medications`
- `vcf_uploads` — filename, SHA-256, uploader, parse/analysis status
- `variants` — includes `source_type`: `CURATED_DATASET` | `UPLOADED_VCF` | `UPLOADED_TXT`
- `variant_annotations`, `ml_predictions`, `acmg_interpretations`, `reconciliations`
- `reports` — JSON payload; lab reviews append a new row
- `knowledge_graph_entities` / `knowledge_graph_relationships`
- `therapy_results`
- `provenance_blocks` — hash chain
- `audit_logs`
- `variant_observations` — real sample timepoints only
- `model_registry` — seeded from `models/registry/*.json` (no invented metrics)

## Relationships

`PATIENT → FILE → VARIANT → INTERPRETATION → REPORT`

Curated catalog rows use a shared `file_type=curated` upload and are never treated as observed genotype.

## Persistence

Workup, uploads, interpretations, graphs, provenance, and reports survive refresh, logout, and process restart as long as the same `clinical.db` file is used.
