# Reanalysis

GenoGuide does not interpret a genome once. Evidence sources change.

```
Evidence sources (local receipts / official downloads)
        ↓
Version tracker (`evidence_source_versions`)
        ↓
Change detector (fingerprint of DATASET_INFO.json / files)
        ↓
Affected interpretation rows
        ↓
Reinterpretation queue (`reanalysis_jobs` / `reanalysis_changes`)
        ↓
Diff + watchlist trigger
        ↓
Human review (never auto-finalize)
```

## API

- `POST /api/v1/reanalysis/check`
- `POST /api/v1/reanalysis/run`
- `GET /api/v1/reanalysis/jobs/{job_id}`
- `GET /api/v1/reanalysis/changes`

Sources are **not scraped**. Fingerprints come from local `research/data/raw/*/DATASET_INFO.json`
and `configs/clingen`. MONDO / literature connectors report `SOURCE_NOT_CONFIGURED`
until real files exist.

## Watchlist

`POST /api/v1/watchlist` records patient/case/variant. On source change the
status becomes `WATCH_TRIGGERED` with `review_required=true`. A finalized
classification is **not** rewritten.

## Interpretation diff

`GET /api/v1/interpretations/{id}/diff/{a}/{b}` is deterministic: new/removed
evidence, ACMG criteria, model probability, phenotype score, classification,
reviewer decision.
