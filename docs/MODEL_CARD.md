# Model card — genoguide-tabular-logreg-v0.1.0

**Purpose:** research-only 5-class pathogenicity *prioritization* on structured
variant features. Not for diagnosis or treatment.

**Intended use:** rank variants for human review; sit beside ACMG, never instead of it.

**Non-intended use:** clinical sign-out, somatic oncology, CNV/SV, prenatal diagnosis,
population screening claims, any setting where gnomAD v4 AF is required and unavailable.

## Training data

- Source: NCBI ClinVar variant_summary (GRCh38 rows), processed locally.
- Labels: 5-class ClinicalSignificance mapped to P / LP / VUS / LB / B.
- Label confidence tiers preserved (expert panel → conflicting). Training uses
  all mapped rows; expert-panel subset is a holdout metric, not the only train set.
- Features: consequence/type one-hots, gnomAD v4.1 constraint (LOEUF/pLI/mis-z),
  ClinGen validity counts, AlphaMissense score when present, log AF when present.
- **ClinVar class is not a feature.**

## Headline metrics (gene-disjoint test, n=120,000 sampled; recorded)

| | logreg (selected) | xgboost |
|---|---|---|
| macro AUPRC | 0.572 | 0.558 |
| macro AUROC | 0.898 | 0.897 |
| MCC | 0.610 | 0.592 |
| ECE (temperature-calibrated) | 0.116 | 0.068 |
| binary P-spectrum vs B-spectrum AUPRC | 0.937 | 0.937 |

Expert-panel holdout is substantially harder (logreg accuracy 0.60, MCC 0.48) —
do not quote the 5-class accuracy as clinical performance.

## Calibration / OOD

Temperature scaling fit on validation only. Mahalanobis distance in feature
space flags OUT_OF_DISTRIBUTION → human review.

## Known failure modes

- VUS vs LP/LB confusion (majority class + label noise).
- Gene-mechanism proxies mis-fire PVS1/PP2 when ClinVar counts are sparse.
- Shared in-silico features (AlphaMissense) inflate apparent ML–ACMG concordance.
- No ESM-2 sequence features in this artifact.
- Population AF is not gnomAD v4 sites.

## Populations

ClinVar is biased toward European-ancestry submissions and well-studied genes.
Gene-disjoint evaluation measures cross-gene generalization, not ancestry fairness.
Ancestry-stratified metrics: **NOT COMPUTED** (no self-reported ancestry on rows).
