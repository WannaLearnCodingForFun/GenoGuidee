# Variant pipeline

## Sources (never mixed in the UI)

| source_type | Meaning | UI label |
|---|---|---|
| `CURATED_DATASET` | ClinVar catalog / phenotype-gene match | CANDIDATE VARIANT — NOT CONFIRMED IN PATIENT |
| `UPLOADED_VCF` | Parsed from a patient VCF | PATIENT OBSERVED VARIANT |
| `UPLOADED_TXT` | Parsed from a documented TXT format | PATIENT OBSERVED VARIANT |

## Ingest

Parser: `backend/app/ingest.py` + `backend/app/bioinformatics/vcf.py`

- VCF 4.x: CHROM, POS, REF, ALT, QUAL, FILTER, INFO, FORMAT, GT, zygosity, VAF when present
- TXT: `chr17:pos:ref:alt`, `17 pos ref alt`, or `GENE:c.HGVS`
- Malformed files return HTTP 422 with the parser error
- Stored: filename, SHA-256, uploader, timestamp, parse status

HGVS-only lines without coordinates are stored but ACMG/ML are `NOT_EVALUABLE`. Coordinates are never invented.

## Interpretation

ESM-2 (real sequence only) → production XGBoost → calibration → ACMG v2 → reconciliation.

ML never overrides ACMG. Discordance is shown as DISCORDANT / human review required.
One stored interpretation object is returned to every UI surface.
