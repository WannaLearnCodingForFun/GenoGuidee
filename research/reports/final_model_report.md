# Final model report (tabular baselines on ClinVar)

**Experiment:** `exp-20260822-172523-a8f995` (see `research/experiments/`)
**Headline split:** gene-disjoint (0 gene overlap train↔test)
**Leakage audit:** exact coordinate / VariationID / gene+protein-change overlap = 0 on gene-disjoint (**OK**)
**Selection policy:** primary macro AUPRC → MCC → AUROC; ECE reported, not optimized
**Selected model:** logistic regression (`genoguide-tabular-logreg-v0.1.0`)

## Dataset

Processed ClinVar GRCh38 rows → parquet feature matrix. Train cap 300k /
eval cap 120k **stratified on train/eval partitions only** (no test oversampling).

## Results (gene-disjoint test, calibrated)

See `research/reports/benchmark_table.md` for the numeric table.

Binary pathogenic-spectrum vs benign-spectrum (VUS dropped) is much easier
(AUROC ~0.98, AUPRC ~0.94) than 5-class (macro AUPRC ~0.57). That is expected:
LP vs P and LB vs B are poorly separated in ClinVar.

## Ablation

AlphaMissense-on vs off: **NOT RUN in this experiment** (AM store may be absent).
Run `genoguide benchmark --all` after converting AM to parquet.

## ESM / multimodal / ensemble

**NOT TRAINED.** Interfaces: `research/training/esm_representation.py`.
Do not cite demo-hash embeddings as results.

## Calibration / OOD

Temperature scaling reduced XGBoost ECE 0.085 → 0.068. LogReg remains
over-confident (ECE 0.116 after scaling). OOD states recorded on the test
feature cloud (Mahalanobis).

## Error analysis

5-class confusion is dominated by VUS↔LB and LP↔P. Expert-panel holdout
MCC drops to ~0.48 — the model is a **prioritizer**, not a VCEP.

## Limitations / future work

gnomAD v4 sites, VEP/MANE transcripts, protein sequences + frozen ESM-2,
official VCEP YAMLs, ancestry-stratified metrics, LightGBM/RF/MLP full sweep.
