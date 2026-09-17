# GenoGuide — Safety checkpoint (baseline)

**Captured:** 2026-09-17  
**Git branch:** `main` (tracking `genoguidee/main`)  
**HEAD:** `aa7f34a43287479dbbec500b6e7c1d3b06463a2e`  
**origin/main:** `3628fa7a1c6de64c42f866adad8d083ed417ab50` (diverged — local main is ahead of `origin`, in sync with `genoguidee/main`)  
**Working tree:** dirty (uncommitted longitudinal / genomic-timeline / model-evaluation work). Not part of this checkpoint commit set.

Command recorded:

```bash
git status
git branch
```

See `docs/SAFE_UPGRADE_AUDIT.md` for architecture. This file is the numeric gate before feature work.

---

## baseline_tests

```
backend/.venv/bin/python -m pytest
```

| Metric | Value |
|---|---|
| Collected | 150 |
| Passed | 148 |
| Skipped | 1 (`tests/test_b8_rls_access_matrix.py` — live Supabase) |
| Failed | 1 (`tests/test_diagnose_sync.py::test_git_head_matches_origin_main_when_on_main`) |

**Pre-existing failure (not introduced by this upgrade):** the test asserts `HEAD == origin/main`. This checkout tracks `genoguidee/main` (`aa7f34a`), not `origin/main` (`3628fa7`). Do not “fix” by rewriting git history.

Safety suite (`tests/test_safety.py`) passed: ML cannot override ACMG; empty evidence is VUS not benign; OOD escalates review.

---

## baseline_api_health

TestClient against `app.main:app` (no extra server process):

| Path | Status | Notes |
|---|---|---|
| `GET /health` | 200 | backend, acmg, ml, research, therapy, database, provenance, vcf_parser, knowledge_graph = READY; ngrok = NOT_CONFIGURED |
| `GET /api/status` | 200 | DEMO_MODE; ACMG Engine (v1, 13 criteria) ready; demo XGBoost ready; ESM-2 demo-precomputed |
| `GET /api/v1/health` | 200 | `engine=genoguide-research`, `acmg_engine=2.0.0`, `kg_version=kg-v1.0.0` |

---

## baseline_build

Python imports of fastapi / sklearn / xgboost / networkx: **ok**.

---

## baseline_frontend_build

```
cd frontend && npm run build
```

Compiled JS **succeeded**. Typecheck **failed** (pre-existing uncommitted file):

```
src/app/(app)/model-evaluation/page.tsx(157,90): error TS2322:
Type 'unknown' is not assignable to type 'ReactNode'.
```

This page is untracked WIP and is **out of scope** for the upgrade (Rule 4: do not rewrite the frontend). Recorded so it is not blamed on new backend work.

---

## Smoke tests

The repository already has a substantial pytest suite (`pytest.ini` → `tests/`). No additional smoke tests were required *before* modifications. New platform tests are added **with** each feature, plus `python -m genoguide regression-test` after the CLI shim exists.

---

## Gate

Upgrade work may proceed. Any regression against the 148 passing tests (other than the documented git-sync assertion) is a stop-the-line defect.
