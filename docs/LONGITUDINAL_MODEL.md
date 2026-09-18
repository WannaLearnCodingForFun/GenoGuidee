# Longitudinal model

Decision-support only. Not a medical device. Not a mortality model.

## What is stored

Each assigned upload creates an immutable `genomic_test_snapshots` row (`test_number` 1, 2, 3…).
A later upload never updates an earlier snapshot identity.

`variant_observations` now carry:

- `snapshot_id`
- `canonical_variant_id` (`GRCh38:17:43057062:T>G`)
- VAF, ACMG class, ML class probabilities, trajectory components

Legacy `GET /api/clinical/patients/{id}/longitudinal` still returns observed VAF points only.

## Canonical identity

`backend/app/services/variant_normalize.py`

`chr17:43057062 T>G` and `17:43057062 T>G` are the same variant.
HGVS-only rows without coordinates use `GRCh38:GENE:c.HGVS` and are not invented coordinates.

## Scoring (transparent)

Weights: `configs/longitudinal.yaml`

**Variant trajectory (0–100)**  
pathogenicity + ACMG severity + VAF trend + persistence + evidence confidence.

**Patient genomic risk**  
Weighted aggregation. Pathogenic ≫ VUS ≫ benign. Not a mean of all variants.

Trend: `IMPROVING | STABLE | WORSENING | MIXED | UNCERTAIN`  
One snapshot → `UNCERTAIN`.

## Comparison

`LongitudinalComparisonEngine` (`services/longitudinal_compare.py`)

- newly detected
- persistent
- **Not detected in current sample** (not “mutation disappeared”)
- reclassified
- VAF / ML / ACMG evidence deltas

## Forecast

`services/risk_forecast.py`

- &lt; 3 snapshots: unavailable
- linear regression; Theil–Sen when n≥4 and fit is noisy
- returns forecast, CI, model name, n, confidence
- optional threshold crossing in *testing intervals*
- `mortality_prediction: false` always

Never display “death in X months.”

## Therapy

`GET .../genomics/therapy-relevance` notes when ACMG class changes.
Rankings still come from `Medical_DrugRecommendation` / stored `therapy_results`.
Language: potentially relevant, requires clinician review.

## Synthetic demo

`POST /api/clinical/demo/longitudinal` (doctor / lab) or `scripts/seed_longitudinal_demo.py`

Patient is marked `synthetic`. Four tests (2026-01-15 … 2026-07-15). Five scripted trajectories.

## Outcome / survival

**Not implemented.** API `outcome.supported` is always false.
