# Data card — GenoGuide training / evidence stores

## Sources (see also docs/DATA_LICENSES.md)

| Name | Role | License | In git? |
|---|---|---|---|
| ClinVar variant_summary + GRCh38 VCF | labels, PS1/PM5 lookups | US public domain | no (manifest + checksums) |
| gnomAD v4.1 constraint | gene features | CC0 | no |
| ClinGen gene-disease validity | gene/KG | CC0 | no |
| HPO + phenotype.hpoa + genes_to_phenotype | phenotype | attribution | no |
| AlphaMissense hg38 | optional feature | **CC BY-NC-SA 4.0** | no |
| REVEL / SpliceAI / CADD / gnomAD sites | connectors only | various | no |

## Label methodology

ClinVar `ClinicalSignificance` is mapped to five classes. `ReviewStatus` becomes
a confidence tier. Conflicting interpretations are **kept**, not majority-voted
away. Aggregate labels are never the sole ACMG input.

## Known biases

- ClinVar over-represents hereditary cancer and well-reimbursed genes.
- Review-status quality is uneven; single-submitter rows dominate.
- LastEvaluated ≠ first submission (temporal split caveat).
- Mechanism flags derived from pathogenic-variant *counts*, not VCEP texts.

## Missingness

Per-variant gnomAD v4 AF, REVEL, SpliceAI, CADD, and protein sequences are
typically missing. The engine records `SOURCE_NOT_CONFIGURED` / `NOT_EVALUABLE`.

## Versioning

Every interpretation records `annotation_version`, ClinVar processing date
(in receipts), ACMG rule version, model id/hash. Dataset fingerprints live in
`models/registry/*.json`.
