# GenoGuide — Safe Upgrade Audit

**Audit date:** 2026-09-17  
**Repository:** https://github.com/WannaLearnCodingForFun/GenoGuidee (local `main` @ `aa7f34a`, remote `genoguidee/main`)  
**Working tree:** dirty — uncommitted longitudinal / genomic-timeline work is present and must not be discarded.  
**Rule:** this document is the gate. No new feature implementation starts until it is complete.

This is **not** a rewrite. GenoGuide already has two stacked systems. The upgrade must add continuous-interpretation capabilities **around** them.

---

## 1. Current architecture

Two APIs share one FastAPI process (`backend/app/main.py`):

| Layer | Surface | Data | Auth | Must remain |
|---|---|---|---|---|
| Legacy demo | `/api/*` | Synthetic 120 variants + 3 patients (`dataset.py`) | none on demo routes | **FROZEN contract** |
| Clinical app | `/api/auth/*`, `/api/clinical/*`, `/api/patient/*` | SQLite `clinical.db` | local PBKDF2 bearer or Supabase JWT | **FROZEN contract** |
| Research engine | `/api/v1/*` | ClinVar/HPO/ClinGen/gnomAD constraint parquet | `X-Role` (architecture) + real token on interpret/family | **FROZEN existing paths** |
| Therapy | `/api/v1/therapy/*`, Medical_DrugRecommendation | CIViC + DGIdb | optional | default-off remote; local ranker |

```
AUTH → RBAC → SQLite clinical store → PATIENT → CLINICAL DATA
  → VARIANT SOURCE (CURATED_DATASET | UPLOADED_VCF | UPLOADED_TXT)
  → annotation → ESM-2 (when live) → tabular ML → ACMG v2 (authoritative)
  → reconciliation (ML never overrides) → report
       ├── therapy ranking (advisory)
       ├── NetworkX knowledge graph
       ├── hash-chained provenance v1 (demo) + v2 (research)
       └── longitudinal snapshots (uncommitted working-tree work)
```

Frontend: Next.js App Router 16 (`frontend/`). Independently designed. **Do not rewrite.**

CLI: `python -m cli.genoguide …` (there is **no** `python -m genoguide` yet).

---

## 2. Existing features (already implemented)

Do **not** reimplement these; extend them.

| Capability | Location | Notes |
|---|---|---|
| ACMG/AMP 2015, 28 criteria | `interpretation/acmg_v2.py` | Missing → `NOT_EVALUABLE`. PP5/BP6 off by default. Strict Table 5 combining. Conflicting P+B → VUS |
| ACMG v1 13-criterion | `acmg.py` | Demo `/api/analyze` only |
| ML tabular (logreg/XGBoost) | `services/ml_predict.py`, `models/` | Gene-disjoint ClinVar. Calibration + Mahalanobis OOD exist |
| Demo XGBoost + hash ESM | `ml.py` | Synthetic; **not** clinical SOT |
| Evidence assembly | `services/evidence.py` | ClinVar parquet, constraint, AM optional; gnomAD sites / REVEL / SpliceAI / CADD = `SOURCE_NOT_CONFIGURED` |
| Reconciliation | `interpretation/reconcile.py` | `final_classification` always ACMG |
| HPO phenotype match / gene / disease rank | `phenotype/{ontology,similarity}.py` | Resnik/Lin/Jaccard; does not alter ACMG |
| Family trio / compound-het / couple | `phenotype/family.py` | Phase unknown unless both parents provided; de novo ≠ PS2 |
| Knowledge graph | `knowledge_graph/graph.py` | NetworkX; ClinGen + HPO; Neo4j hook |
| Provenance v1 | `provenance.py` | Demo SQLite chain |
| Provenance v2 | `provenance2/ledger.py` | hashes + versions; no genomic payload |
| Clinical RBAC | `local_auth.py` + `clinical_db.can_access_patient` | doctor / patient / lab_technician |
| V1 role primitives | `api/v1.py` `X-Role` | PATIENT, DOCTOR, LAB_CLINICIAN, RESEARCHER, GENETIC_COUNSELOR, ADMIN — **not production auth** |
| VCF validate/normalize | `bioinformatics/vcf.py` | left-align needs FASTA+bcftools |
| Longitudinal timeline | uncommitted `services/longitudinal*.py` | treat as existing; do not clobber |
| Therapy ranking | `services/drug_recommendation.py` | never ACMG/PGx |
| Audit logs | `audit_logs` table | clinical actions |
| Model registry | `model_registry` + `models/registry/*.json` | |

### Explicit NOT IMPLEMENTED (do not fake)

- Continuous reanalysis / watchlist / interpretation versioning
- Evidence conflict radar as a first-class aggregator
- Human curation state machine (AI_DRAFT → FINALIZED)
- ACMG what-if simulator
- GA4GH Phenopackets
- De-identified cohort researcher mode
- Model drift monitoring service
- Phenotype evolution over time (table has no onset/status/negation)
- Evidence-grounded claim list (current explanation is a stub)
- Hyperledger Fabric, Neo4j, live ESM-2 in production interpret, LLM classifier
- OMIM / GeneReviews / DisGeNET / PharmGKB
- `python -m genoguide doctor|regression-test|demo-regression`

---

## 3. Existing API endpoints

### Frozen legacy (`backend/app/main.py`)

`GET /health`, `/health/detailed`, `/api/health`, `/api/status`, `/api/stats`  
`GET /api/variants`, `/api/variants/{id}`  
`POST /api/analyze`, `/api/analyze/uploaded`, `/api/workup`  
`GET /api/patients`, `/api/patients/{id}`, `/api/patients/{id}/context`, `/api/graph/{id}`  
`GET /api/provenance/audit`, `POST /api/provenance/verify`, consent record/revoke

### Frozen clinical (`backend/app/clinical_routes.py`)

Auth, patient identity, workup, uploads, variants, curated interpret, graph, provenance, consent, audit, reports, longitudinal/genomics timeline, model evaluation, therapy/system health.

### Frozen research v1 (`backend/app/api/v1.py`) — do not rename

`GET /api/v1/health`, `/system/status`, `/models/status`  
`POST /api/v1/variants/normalize|annotate|batch`, `GET /variants/{id}`  
`POST /api/v1/interpret`, `/interpret/batch`, `GET /interpret/{id}`  
`POST /api/v1/acmg/evaluate`, `GET /acmg/rules`  
`POST /api/v1/phenotype/match`, `/phenotype/gene-ranking`, `/phenotype/disease-ranking`  
`GET /api/v1/graph/gene/{gene}`, `POST /graph/query`  
`GET/POST /api/v1/provenance/{id}`  
`GET /api/v1/research/datasets|models|benchmarks`  
`POST /api/v1/vcf/validate|normalize`  
`POST /api/v1/family/trio|couple`  
`GET /api/v1/interpret/{id}/evidence|explanation` (explanation is a stub)  
`/api/v1/therapy/*`, `/api/v1/frontend/*`

### New endpoints to add (additive only)

Under `/api/v1/`: `evidence`, `reanalysis`, `watchlist`, `phenotypes`, `inheritance`, `acmg/simulate`, `curation`, `cases`, `phenopackets`, `cohorts`, `model-monitoring`, expanded `graph`, `interpretations/{id}/history|diff`.

CORS today allows **GET, POST, OPTIONS** only. New mutating APIs must be POST (or CORS must be extended carefully). Clinical `PATCH` already exists — do not “fix” CORS as a drive-by.

---

## 4. Existing database tables

Store: SQLite `backend/app/clinical.db` via `clinical_db.py`. `GENOGUIDE_CLINICAL_DB` override. **Do not DROP TABLE / DROP DATABASE.**

**Core:** `users` (CHECK role IN doctor|patient|lab_technician), `patients`, `patient_assignments`, `patient_invitations`, `patient_phenotypes`, `family_history`, `medications`, `vcf_uploads`, `variants`, `variant_annotations`, `ml_predictions`, `acmg_interpretations`, `reconciliations`, `knowledge_graph_entities`, `knowledge_graph_relationships`, `therapy_results`, `provenance_blocks`, `reports`, `workup_snapshots`, `variant_observations`, `genomic_test_snapshots`, `report_revisions`, `patient_trajectory_summaries`, `model_registry`, `audit_logs`.

**Second SQLite:** `backend/app/genoguide.db` — demo provenance v1 + research `ledger_v2`. Do not merge destructively.

**Migration style already used:** `CREATE TABLE IF NOT EXISTS` + `_add_col`. New upgrade tables must follow the same pattern.

**Constraint to respect:** `users.role` CHECK cannot gain genetic_counselor/researcher/admin without recreating the table. Extended roles go in a **new** mapping table, not a CHECK rewrite.

**Phenotype gap:** `patient_phenotypes` has `phenotype, hpo_id, source, created_at` — no status, onset, observed_at, confidence, negation.

---

## 5. Existing frontend routes

| Path | Role visibility |
|---|---|
| `/` marketing | public |
| `/login`, `/signup/*` | public |
| `/dashboard` | all |
| `/clinical-workup` | doctor |
| `/variant-lab` | doctor, lab |
| `/patient-context` | all clinical roles |
| `/therapy` | doctor |
| `/knowledge-graph` | doctor |
| `/provenance` | all |
| `/upload` | all |
| `/genomic-timeline` (+ `[patientId]`) | all (uncommitted) |
| `/model-evaluation` | doctor, lab (uncommitted) |
| `/unauthorized` | fallback |

**Do not remove or redesign these.** New capabilities ship as APIs first. Any UI is optional and additive.

Nav: `frontend/src/lib/nav.ts`. API client: `frontend/src/lib/api.ts`.

---

## 6. Existing ML pipeline

1. **Clinical/research inference:** `services/ml_predict.py` + `services/interpret.py` — registered joblib, calibrated probabilities, entropy/max-prob, Mahalanobis OOD when detector present. Never overrides ACMG.
2. **Training:** `research/training/train_baselines.py`, leakage-safe splits, `configs/model.yaml`.
3. **Demo:** `ml.py` XGBoost on synthetic `_sample_variant`.
4. **ESM-2:** live path requires torch + fair-esm + `GENOGUIDE_MODE=live`. Default is demo embeddings.
5. **NOT trained:** LightGBM/RF/MLP in last recorded experiment; multimodal; stacked ensemble.

Upgrade must **expose** calibrated_probability / entropy / uncertainty / OOD_score / model_version on new monitoring + interpret extras without changing the demo `/api/analyze` payload.

---

## 7. Existing blockchain / provenance pipeline

- **v1** (`provenance.py`): hash chain of interpretation/consent payloads. Demo UI.
- **v2** (`provenance2/ledger.py`): `input_hash`, annotation/model/ACMG/KG/phenotype versions, `evidence_snapshot_hash`, `output_hash`, operator. Chain = SHA256(index|prev|payload|ts).
- Clinical `provenance_blocks` for patient-scoped events.
- **Not Fabric.** Do not fake on-chain txs.

Upgrade: additive provenance object fields + new version rows. Never rewrite v1/v2 tables.

---

## 8. Dependencies

**Backend** (`backend/requirements.txt`): fastapi, uvicorn, xgboost, scikit-learn, numpy, pydantic, pandas, pyyaml, duckdb, joblib, networkx, rich, httpx, pytest, python-multipart.

**Live optional:** torch, fair-esm (`requirements-live.txt`).

**Frontend:** next 16.3.1, react 19, supabase-js, framer-motion, recharts, three.

**Therapy:** isolated `Medical_DrugRecommendation/requirements.txt`.

**No phenopackets library** in tree. Implement a minimal GA4GH-shaped adapter; do not add a heavy unused dependency unless tests need it.

---

## 9. Known bugs / debt (do not “fix” unless required)

From `docs/TECHNICAL_DEBT.md` plus this audit:

1. Population AF is ClinVar VCF ExAC/1000G/ESP, not gnomAD v4 sites.
2. Gene mechanism flags are ClinVar count proxies, not VCEP.
3. PP3 can share AlphaMissense with ML features (circular concordance).
4. `X-Role` is not authentication; interpret already requires a real token.
5. CORS methods omit PATCH/PUT even though clinical PATCH exists.
6. Knowledge graph is on-demand NetworkX, not persisted with evidence provenance on every edge.
7. Explanation endpoint does not map claims → evidence IDs.
8. Demo and research share conceptual confusion between `clinical.db` and `genoguide.db`.
9. Working tree has uncommitted longitudinal files — merge-conflict risk if those files are rewritten.
10. Accidental untracked `frontend/frontend@0.1.0` and `frontend/next` must **not** be committed.

---

## 10. Integration points (safe hooks)

| New feature | Hook into | Do not replace |
|---|---|---|
| Evidence graph | `knowledge_graph.graph.NODE_TYPES/EDGE_TYPES`, clinical KG tables | `build_gene_graph` return shape used by `/api/graph` and `/api/v1/graph/gene` |
| Conflict radar | `EvidenceService.source_summary` + ACMG + ML + phenotype | reconcile invariants |
| Interpretation versions | wrap `InterpretationService.interpret` + ledger v2 id | `POST /api/v1/interpret` response schema |
| Reanalysis | evidence fingerprints (`DATASET_INFO.json`, parquet mtime/hash) | silent ClinVar download |
| Watchlist | clinical variants + reanalysis changes | auto-finalize |
| Phenotype-first | `ontology.resolve`, `rank_genes`, `rank_diseases` | ACMG classification |
| Phenotype evolution | ALTER `patient_phenotypes` add columns | drop/recreate table |
| Inheritance | `phenotype.family` | invent phase |
| ACMG simulator | `acmg_v2.combine` / `evaluate` | persist as official |
| Curation | new tables + audit_logs | overwrite `acmg_interpretations` in place |
| RBAC | map clinical roles ↔ v1 permission roles; extra roles table | users CHECK constraint |
| Phenopackets | adapter over patients/phenotypes/variants | replace patient schema |
| Explanations | structured from ACMG criteria + sources | LLM classification |
| OOD / drift | `research.training.uncertainty` + prediction logs | silent retrain |
| Provenance upgrade | extra fields on new version rows; still call ledger v2 | replace v1 chain |

---

## 11. Files that must not be modified

Unless a one-line mount/flag is unavoidable:

- `backend/app/dataset.py` — synthetic showcase
- `backend/app/ml.py` — demo XGBoost
- `backend/app/acmg.py` — ACMG v1
- `backend/app/provenance.py` — ledger v1
- `backend/app/clinical.py` — demo clinical narratives
- Legacy route handlers in `backend/app/main.py` (`/api/analyze`, `/api/variants`, …)
- Existing handler signatures/response models in `backend/app/api/v1.py` and `clinical_routes.py`
- `frontend/src/app/**` pages (no redesign)
- `Medical_DrugRecommendation/**` (therapy engine)
- `research/data/raw/**` (never commit)
- Accidental `frontend/frontend@0.1.0`, `frontend/next`

**Prefer new files** under `backend/app/platform/` and `backend/app/api/platform.py`.

---

## 12. Potential breaking changes (must avoid)

| Change | Why it breaks | Mitigation |
|---|---|---|
| Rename `/api/v1/phenotype/*` to `/phenotypes/*` | CLI + tests + docs | keep old paths; add new aliases |
| Change `InterpretationObject` field names | API contract | additive fields only |
| Expand `users.role` CHECK | requires table rebuild | `user_platform_roles` table |
| Persist simulations into `acmg_interpretations` | contaminates clinical SOT | separate non-official store or no persist |
| Auto-update finalized classification on reanalysis | clinical safety | queue + human review only |
| Graph edge without provenance | product rule | reject unsigned evidence edges |
| Frontend nav/role matrix rewrite | UI regressions | APIs first |
| Default-on remote therapy / silent dataset download | pytest/offline | flags default so legacy still works offline |
| DROP TABLE in migrations | data loss | CREATE IF NOT EXISTS + ADD COLUMN only |
| Commit longitudinal WIP unintentionally | unrelated diff | stage only upgrade files |

---

## 13. Feature-flag policy

All major new features behind env flags (see `.env.example`).  

**When every new flag is false:** legacy `/api/*`, clinical `/api/clinical/*`, and existing `/api/v1/*` handlers behave as today. New routers return structured `FEATURE_DISABLED`.

---

## 14. Git / branch policy for this upgrade

- Current branch: `main` (tracks `genoguidee/main`).
- Dirty tree includes longitudinal feature work — **do not** `git checkout` in a way that drops it.
- Requested logical commits (`feat/evidence-graph`, …) will be **commit messages on main** (or stacked commits) rather than discarding WIP to create empty branches.
- Do not commit `.DS_Store`, secrets, raw datasets, or accidental `frontend/next`.

---

## 15. Test inventory (regression must keep passing)

`tests/test_api.py`, `test_acmg.py`, `test_safety.py`, `test_showcase.py`, `test_provenance.py`, `test_vcf.py`, `test_schema.py`, `test_splits.py`, `test_family.py`, `test_health.py`, `test_clinical_pipeline.py`, `test_patient_identity.py`, `test_b3_acmg_v2_authoritative.py`, `test_b8_phi_boundary.py`, `test_b8_rls_access_matrix.py`, `test_b9_remote_shared_secret.py`, `test_therapy_*.py`, `test_drug_recommendation.py`, `test_frontend_bridge.py`, `test_ml_prediction_consistency.py`, `test_esm.py`, `test_diagnose_sync.py`, plus uncommitted `test_longitudinal.py`.

Safety invariants already tested: ML cannot override ACMG; empty evidence → VUS not benign; OOD escalates review.

---

## 16. Implementation order (locked)

P0: flags + regression CLI → evidence graph → conflict radar → interpretation versioning/diff → reanalysis + watchlist → human curation + RBAC tests.

P1: phenotype-first + evolution → inheritance solver → ACMG simulator → grounded explanation → provenance upgrade.

P2: phenopackets → cohorts → model monitoring / OOD surface → evidence timeline.

---

## 17. Verdict

The repository is a **hackathon demo + research engine + clinical SQLite app**. Most “platform” nouns already exist in partial form. The upgrade is a **continuous-interpretation layer** (versions, diffs, reanalysis, curation, evidence graph provenance) with **strict additive APIs and migrations**.

**Status:** audit complete. Baseline capture is the next gate.
