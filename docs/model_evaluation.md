# Model evaluation (real, held-out)

Generated: 2026-08-23T00:15:16.526735+00:00

## Task (headline)

Binary **pathogenic-spectrum** (P+LP) vs **benign-spectrum** (B+LB) on ClinVar
GRCh38 rows with `meta_confidence_tier >= 2`. VUS and conflicting
interpretations are excluded. Features never include review status or raw
clinical significance.

## Split

Gene-disjoint (seed 62). Leakage audit: **OK**.
Exact coordinate overlap: 0.
VariationID overlap: 0.

n_train=290727 n_val=38801 n_test=58481

## Held-out TEST (gene-disjoint)

| Metric | Value |
|---|---|
| accuracy | 0.9057 |
| balanced accuracy | 0.9224 |
| precision | 0.7281 |
| recall | 0.9539 |
| F1 | 0.8259 |
| ROC-AUC | 0.9786 |
| PR-AUC | 0.9467 |
| n | 58481 |
| confusion [[TN,FP],[FN,TP]] | [[39896, 4881], [632, 13072]] |
| decision threshold (from val) | 0.175 |

Validation (same threshold): accuracy=0.9233 balanced_accuracy=0.9352

## 5-class production model (not this artifact)

5-class gene-disjoint accuracy is recorded in benchmark_results.json (~0.75). That is NOT this binary task.

Do not report 5-class accuracy as 85% unless that number appears in the 5-class
benchmark file.

## Model

XGBoost binary:logistic, n_estimators=400, max_depth=6, lr=0.08, hist.
Artifact: `models/production/xgboost_hq_binary.joblib`
