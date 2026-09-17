# Changelog

## 2026-09-17 — Continuous interpretation layer (additive)

- Audit: `docs/SAFE_UPGRADE_AUDIT.md`, baseline: `docs/BASELINE.md`.
- Feature-flagged `/api/v1` platform: evidence graph, conflict radar, interpretation
  versioning/diff, reanalysis, watchlist, phenotype-first + evolution, inheritance
  solver, ACMG simulator, human curation, phenopackets adapter, de-identified
  cohorts, model drift/OOD monitoring, evidence timeline, provenance object.
- CLI: `python -m genoguide doctor|regression-test|demo-regression`.
- Existing `/api/*`, `/api/clinical/*`, and prior `/api/v1/*` handlers preserved.
- Frontend not rewritten.
- No DROP TABLE / DROP DATABASE. Platform tables are `CREATE IF NOT EXISTS`.

Clinical safety: ML still cannot override ACMG; missing ≠ benign; simulations
are not official; reanalysis does not auto-finalize.
