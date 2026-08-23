# Datasets

See also `docs/datasets.md` and `data/MANIFEST.md`.

Do not commit multi-gigabyte raw files. Download locally:

```
backend/.venv/bin/python scripts/download_datasets.py
backend/.venv/bin/python scripts/build_variant_database.py
```

## Sources used (when cached locally)

| Dataset | Role | License note |
|---|---|---|
| NCBI ClinVar GRCh38 | variant labels + catalog search | public / NCBI terms |
| gnomAD constraint metrics | population constraint features | gnomAD terms |
| HPO genes_to_phenotype | phenotype → gene candidates | HPO |
| AlphaMissense (optional) | functional score if file present | DeepMind terms |

## Development fixtures

`tests/data/mini.vcf` and TXT strings in `tests/test_clinical_pipeline.py` are **test fixtures**, not clinical patients.

No synthetic clinical patients are seeded into the production/demo database path.
