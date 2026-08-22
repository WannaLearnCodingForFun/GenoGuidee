# GenoGuide — Technical Debt (research engine)

Verified against code. Items marked FIXED were true of the demo and are addressed in the research path; the demo path still has them.

## SEVERE (research claims)

1. **Population AF is not gnomAD v4.** When `population_af.parquet` exists it is built from ClinVar VCF INFO (legacy ExAC/1000G/ESP). PM2/BA1/BS1 therefore use outdated cohorts. gnomAD sites remain SOURCE_NOT_CONFIGURED (TB-scale). *Mitigation: engine records the source string; missing gnomAD does not invent absence.*
2. **Gene mechanism flags are ClinVar count proxies**, not VCEP assertions (documented in `MECHANISM_POLICY`). PVS1/PP2/BP1 can fire on those proxies.
3. **PS1/PM5 lookups exclude the query variant but use ClinVar pathogenic labels** — circular if the same ClinVar record is both training label and ACMG evidence. Interpretation path uses them as *evidence*, training features do **not** include the ClinVar class (feature schema is consequence/gene/AM/AF only). Keep it that way.
4. **No protein sequences** → ESM-2 delta embeddings not used in production inference (`sequence_model.availability = NOT_IMPLEMENTED`).
5. **Headline benchmark trained logreg+xgboost only** (config lists RF/LGBM/MLP). Re-run `genoguide benchmark --all` after installing lightgbm if those numbers are needed.

## HIGH

6. **PP3 circularity with ML features.** AlphaMissense (and REVEL if configured) can enter both PP3 and the tabular model. Concordance is partly built-in. Ablation without AM is the correct scientific control.
7. **Temporal split uses LastEvaluated year**, not first ClinVar submission — approximation, caveated in `splits.py`.
8. **Consent not enforced** on legacy `/api/analyze`. Research interpret path does not gate on consent either.
9. **patient_hash in ledger v1** remains unsalted SHA-256 of a short ID.
10. **X-Role header is not authentication.** Replace with OIDC/mTLS before any networked deployment.

## MEDIUM

11. **VEP not run** — consequences come from ClinVar molecular consequence strings, not MANE/canonical VEP.
12. **Pure-Python VCF norm cannot left-align** without a FASTA.
13. **Knowledge graph is on-demand NetworkX**, not a persisted graph DB.
14. **No SHAP in the inference path** (explainability is an extension).
15. **Demo and research share one SQLite file** (`backend/app/genoguide.db`) with two tables — operationally fine, conceptually messy.

## LOW / DEMO-ONLY (quarantined)

16. Synthetic 120-variant dataset + 3 patients + narrative genome funnel numbers.
17. Demo ESM embeddings are seeded vectors.
18. Demo XGBoost trained on the class-conditioned generator.
19. ACMG v1 13-criterion subset still used by the frontend analyze path.
20. Overview 74,305 "variants analyzed" is a sum of narrative constants.
