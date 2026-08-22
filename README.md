# GenoGuide

**Research-grade genomic variant interpretation + precision decision support**
(SIH Problem 62 core, Problem 60 downstream)

The repository contains two layers:

| Layer | Who uses it | Data |
|---|---|---|
| Legacy demo API `/api/*` + `frontend/` | Independently redesigned UI | Synthetic / demo (labeled) |
| Research engine `/api/v1/*` + CLI | Terminal, pytest, training | ClinVar / HPO / gnomAD constraint / ClinGen |

`frontend/` is **read-only** for engine work. Do not modify it here.

This is **not** a medical device. Output is research / decision-support phrasing only.

---

## Quick start (engine)

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# from repo root
export PYTHONPATH=.
python -m cli.genoguide status
python -m cli.genoguide demo
python -m cli.genoguide validate-vcf tests/data/mini.vcf
python -m cli.genoguide interpret --variant 'GRCh38:17:43057062:T>TG'
pytest -q
```

Data is **never** downloaded silently:

```bash
python -m cli.genoguide data list
python -m cli.genoguide data download clinvar_variant_summary
python -m cli.genoguide data verify
```

Train / benchmark (requires processed parquet from the ClinVar pipeline):

```bash
python -m research.preprocessing.build_clinvar_dataset
python -m research.preprocessing.build_training_dataset
python -m cli.genoguide train --config configs/model.yaml
python -m cli.genoguide benchmark --all
python -m cli.genoguide research run
```

---

## What is real vs not

See `docs/CURRENT_ARCHITECTURE.md` and `docs/TECHNICAL_DEBT.md`.

Honest highlights:

- ACMG/AMP 2015 **28 criteria**, missing evidence → `NOT_EVALUABLE` (never MET).
- ML **cannot** override ACMG (`reconciliation.final_classification` is always ACMG).
- Gene-disjoint ClinVar benchmark is a **real recorded run** (logreg selected by AUPRC).
- ESM-2 live embeddings, VEP, gnomAD v4 sites, DeepVariant execution, Fabric, and LLMs are **NOT IMPLEMENTED** as production paths (interfaces/docs only).

## License / data

Raw datasets are git-ignored. Licenses: `docs/DATA_LICENSES.md`.
AlphaMissense is **CC BY-NC-SA 4.0** (non-commercial).
