# Variant pipeline audit (2026-08-23)

## Current architecture

```
Upload (VCF/TXT) → clinical.db (vcf_uploads + variants)
                 → optional patient assign
                 → POST /api/clinical/variants/{id}/interpret
                      → InterpretationService (ACMG v2 + tabular ML)
                      → reconciliation (ACMG authoritative)
                      → provenance + report + knowledge graph
```

Parallel leftover path (legacy demo contract, still used by some tests):

```
POST /api/analyze → dataset.py curated variants
                 → app/ml.py DEMO ESM hash vectors + synthetic-trained XGBoost
                 → app/acmg.py demo engine
```

Variant Lab (after clinical wiring) calls `clinicalInterpret`, then **re-derives**
`top_class_key` and treats missing `confidence` as `0`.

## Broken components

1. **Two probability vectors.** `interpret._ml_predict` sets
   `top_class = argmax(calibrated)` but `probabilities = uncalibrated`.
   The UI can highlight a different class than the tallest bar.
2. **Missing confidence.** Clinical mapper reads `max_p` / `confidence`,
   which `MlPrediction` does not set. Frontend then shows `0.0%`.
3. **Hardcoded engine string** `"research-tabular-logreg"` even when the
   registered artifact is XGBoost.
4. **Frontend remapping** `top_class.toLowerCase().replace(...)` is a second
   independent classification.
5. **ESM-2 in Variant Lab** is a placeholder object (`dims: 0`, `not_live`)
   written by the frontend, not the model service.
6. **Production XGBoost artifact exists** (`models/production/xgboost_gene_disjoint.joblib`,
   ClinVar gene-disjoint) but is **not loaded** because the registry only lists logreg.
7. **`app/ml.py` demo XGBoost** is trained on synthetic `_sample_variant` features.
   Must not be the clinical path.
8. **5-class gene-disjoint accuracy is ~75%** (recorded). 85% is not honest on
   5-class including VUS. A high-review P/LP vs B/LB task is the scientifically
   appropriate 85% target.

## Corrected flow

```
variant (coords) → annotation (ClinVar/ClinGen/constraint; no invented AF)
                → ESM-2 if a real protein sequence exists, else UNAVAILABLE
                → XGBoost (ClinVar-trained) → ONE prediction object
                → ACMG v2
                → reconcile (final = ACMG)
                → persist
```

Prediction object (single source of truth):

- `probabilities` (calibrated, sum = 1)
- `predicted_class` = argmax(probabilities)
- `confidence` = probabilities[predicted_class]
- `model_name`, `model_version`, `dataset_version`

Frontend displays these fields only.
