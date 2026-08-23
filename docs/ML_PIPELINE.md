# ML pipeline

Clinical inference uses `backend/app/services/ml_predict.py`, not the synthetic demo `app/ml.py`.

## Architecture

ESM-2 protein embedding (when `torch` + `fair-esm` and a real sequence exist)
→ tabular features → XGBoost → calibrated probabilities → predicted class.

If ESM-2 cannot run: status is `SOURCE_NOT_CONFIGURED` or `NOT_APPLICABLE`. No fake vector is stored.

## Production 5-class UI model

- Artifact: `models/production/xgboost_gene_disjoint.joblib`
- Registry: `models/registry/genoguide-tabular-xgboost-v0.1.0.json`
- Labels: benign / likely_benign / vus / likely_pathogenic / pathogenic
- Gene-disjoint 5-class accuracy is about 75%. **Do not claim 85% for this model.**

## Headline binary model (high-review ClinVar only)

- Artifact: `models/production/xgboost_hq_binary.joblib`
- Registry: `models/registry/genoguide-xgboost-hq-v1.0.0.json`
- Held-out gene-disjoint TEST (n=58481): accuracy **0.9057**, balanced accuracy **0.9224**
- See `docs/model_evaluation.md`

This binary model is **not** the five-bar Variant Lab classifier.

## Label policy

P+LP → pathogenic spectrum. B+LB → benign spectrum. VUS and conflicting ClinVar rows are excluded from the binary trainer. ClinVar significance is a **target**, never a feature.

## Canonical prediction object

`predicted_class == argmax(probabilities)`
`confidence == probabilities[predicted_class]`
`sum(probabilities) == 1`
