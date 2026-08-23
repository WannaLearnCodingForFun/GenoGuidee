# Dataset manifest

Raw genomic files are **not** committed. Receipts live next to each download
as `DATASET_INFO.json`. Authoritative catalog: `research/data/manifest.yaml`.

| Dataset | Source | Typical local path | License |
|---|---|---|---|
| ClinVar variant_summary / VCF | NCBI ClinVar | `research/data/raw/clinvar/` | Public domain (US gov.) |
| ClinGen gene-disease validity | ClinGen | `research/data/raw/clingen/` | CC0 1.0 |
| gnomAD v4.1 constraint | Broad Institute | `research/data/raw/gnomad_constraint/` | CC0 |
| HPO | JAX / Monarch | `research/data/raw/hpo/` | Free with attribution |
| AlphaMissense hg38 | DeepMind / Zenodo | `research/data/raw/alphamissense/` | CC BY-NC-SA 4.0 |

Download:

```bash
python -m cli.genoguide data list
python -m cli.genoguide data download clinvar_variant_summary
python -m cli.genoguide data verify
# or
python scripts/download_datasets.py
```

Processed tables (rebuild, do not invent labels):

```bash
python scripts/build_variant_database.py
```
