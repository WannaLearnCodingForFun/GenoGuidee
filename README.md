# GenoGuide

**Research-grade genomic variant interpretation + precision decision support**
(SIH Problem 62 core, Problem 60 downstream)

The repository contains two layers:

| Layer | Who uses it | Data |
|---|---|---|
| Legacy demo API `/api/*` + `frontend/` | Independently redesigned UI | Synthetic / demo (labeled) |
| Research engine `/api/v1/*` + CLI | Terminal, pytest, training | ClinVar / HPO / gnomAD constraint / ClinGen |

`frontend/` is **not rewritten** for engine work. An additive `/therapy` page
proxies optional somatic oncology ranking; Variant Lab and Patient Context PGx
are unchanged.

This is **not** a medical device. Output is research / decision-support phrasing only.

---

## Optional somatic therapy ranking

Default **off** (offline demo/pytest must not depend on ngrok). Enable:

```bash
# one-shot — pass the LIVE engine host (ngrok-free URLs change every session)
backend/.venv/bin/python -m cli.genoguide therapy \
  --url https://sunshiny-braelyn-unruminated.ngrok-free.dev \
  --gene EGFR --variant p.Leu858Arg --disease "lung adenocarcinoma"

# or env (do not copy a placeholder hostname)
export GENOGUIDE_DRUG_API_ENABLED=true
export GENOGUIDE_DRUG_API_URL=https://sunshiny-braelyn-unruminated.ngrok-free.dev
```

Protein HGVS is mapped (`p.Leu858Arg` → `L858R`); genomic IDs are never guessed.
Rankings do **not** alter ACMG and are not CPIC/PGx. UI: `/therapy`.

---

## Quick start (engine)

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# from repo root — use python3 or the venv (plain `python` is often not on PATH)
export PYTHONPATH=.
backend/.venv/bin/python -m cli.genoguide status
backend/.venv/bin/python -m cli.genoguide demo
backend/.venv/bin/python -m cli.genoguide validate-vcf tests/data/mini.vcf
backend/.venv/bin/python -m cli.genoguide interpret --variant 'GRCh38:17:43057062:T>TG'
backend/.venv/bin/python -m cli.genoguide therapy --demo
backend/.venv/bin/python -m pytest -q
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
- Optional somatic oncology ranking is a **separate connector** (default off). It never overrides ACMG and is not CPIC/PGx.
- ESM-2 live embeddings, VEP, gnomAD v4 sites, DeepVariant execution, Fabric, and LLMs are **NOT IMPLEMENTED** as production paths (interfaces/docs only).

## License / data

Raw datasets are git-ignored. Licenses: `docs/DATA_LICENSES.md`.
AlphaMissense is **CC BY-NC-SA 4.0** (non-commercial).
