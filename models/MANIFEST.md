# Model manifest

## Production 5-class (Variant Lab bars)

| Field | Value |
|---|---|
| Model | `genoguide-tabular-xgboost-v0.1.0` |
| Artifact | `models/production/xgboost_gene_disjoint.joblib` |
| Data | ClinVar GRCh38 `training_dataset.parquet` |
| Split | gene-disjoint |
| Task | 5-class P / LP / VUS / LB / B |
| 5-class accuracy | ~0.75 (see `research/reports/benchmark_results.json`) — **not 85%** |

## High-review binary (85% target)

| Field | Value |
|---|---|
| Model | `genoguide-xgboost-hq-v1.0.0` |
| Artifact | `models/production/xgboost_hq_binary.joblib` |
| Filter | P/LP/B/LB and `meta_confidence_tier >= 2` |
| Split | gene-disjoint, leakage **OK** (0 coordinate / VariationID overlap) |
| Held-out accuracy | **0.9057** |
| Balanced accuracy | **0.9224** |
| Precision | 0.7281 |
| Recall | 0.9539 |
| F1 | 0.8259 |
| ROC-AUC | 0.9786 |
| PR-AUC | 0.9467 |
| n_test | 58481 |
| Threshold (from val) | 0.175 |

See `docs/model_evaluation.md`.

## ESM-2

`esm2_t6_8M_UR50D` when `torch` + `fair-esm` are installed **and** a real protein
sequence is supplied. Otherwise `SOURCE_NOT_CONFIGURED` / `NOT_INSTALLED`.
No hash-fake embeddings on the clinical path.
