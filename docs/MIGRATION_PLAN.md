# GenoGuide — Migration Plan (demo → research-grade engine)

**Non-negotiables**
- `frontend/` is READ-ONLY. Legacy `/api/*` endpoints keep working unchanged.
- New surface is versioned under `/api/v1/`.
- No fabricated data, labels, metrics, or citations. Anything not implementable
  in this environment is marked **NOT IMPLEMENTED** with an extension point.
- Synthetic artifacts remain but are quarantined and labeled.

## Target layout (as adopted)

```
sih/
├── backend/app/
│   ├── main.py                # legacy demo API (preserved verbatim)
│   ├── api/v1/                # new versioned routers
│   ├── schemas/               # canonical pydantic models (variant, interpretation, …)
│   ├── bioinformatics/        # VCF validation/normalization, tool wrappers
│   ├── interpretation/        # ACMG v2 engine, ClinGen spec layer, reconciliation
│   ├── phenotype/             # HPO ontology, IC-based similarity, ranking
│   ├── knowledge_graph/       # NetworkX-backed graph service
│   └── provenance2/           # ledger v2 with reproducibility metadata
├── research/
│   ├── data/{raw,interim,processed,external_holdout}/   (git-ignored)
│   ├── data/manifest.yaml     # dataset registry: source/version/license/checksum
│   ├── preprocessing/         # ClinVar → labeled parquet, feature join
│   ├── training/              # baselines, calibration, model selection
│   ├── evaluation/            # metrics, splits, leakage audit, error analysis
│   └── reports/               # generated artifacts (json/md/csv)
├── models/registry/           # committed metadata; weights git-ignored
├── cli/                       # python -m cli.genoguide …
├── configs/                   # experiment + model YAML configs
├── tests/                     # pytest: unit, integration, API, safety
└── docs/                      # this plan, licenses, cards, API contract
```

Divergences from the idealized tree in the brief: research ML code lives under
`research/` (not `backend/app/ml/`, which would collide with the legacy
`ml.py`); pipeline wrappers live in `backend/app/bioinformatics/` until a real
FASTQ pipeline exists. Documented here so nothing is silently renamed.

## Phase map

| Phase | Scope | Strategy in this environment |
|---|---|---|
| 1 | Audit | this document set |
| 2 | Canonical schema + data acquisition | pydantic schema; manifest-driven download/verify CLI; ClinVar/HPO/gnomAD-constraint/ClinGen fetched for real; AlphaMissense/REVEL/SpliceAI/CADD/gnomAD-sites = scripted connectors (size/registration/licensing) |
| 3 | VCF processing | pure-Python validator + normalizer (trim + multiallelic decomposition); bcftools/VEP wrappers that activate when tools are installed (none are, currently) |
| 4 | Evidence integration | ClinVar variant_summary → labeled parquet with review-status tiers; constraint/ClinGen gene features; connector classes with explicit availability states |
| 5–7 | Training data + splits + baselines | DuckDB feature builder; random/gene/chromosome/temporal splits; leakage audit; LogReg/RF/XGB/LGBM/MLP with full metric suite + calibration; **real ClinVar-derived run** |
| 8–10 | ESM-2 / multimodal / uncertainty | modules implemented; ESM benchmark only if torch installs and a protein sequence source exists — otherwise NOT BENCHMARKED, stated in report; ensemble variance/entropy/Mahalanobis OOD implemented on tabular models |
| 11 | ACMG v2 | 28 criteria as evidence objects with per-criterion applicability/strength/inputs/version; YAML ClinGen specification layer; combining rules; human-review gate |
| 12 | Phenotype | real HPO ontology; IC from phenotype.hpoa; Resnik/Lin/Jaccard; gene & disease ranking |
| 13–15 | KG, clinical evidence, provenance v2 | NetworkX graph from HPO/ClinGen/constraint + interpretation results; considerations with source objects; ledger v2 metadata (input_hash, versions, operator, snapshot hash) |
| 16–17 | API v1 + CLI | routers per resource; role primitives (dependency-based, token stub); `python -m cli.genoguide` with status/data/validate/normalize/interpret/acmg/phenotype/graph/train/benchmark/demo/pipeline |
| 18 | Tests | pytest: unit (schema, VCF, ACMG, phenotype, splits), integration, API, safety (ML-cannot-override, unknown≠benign, missing≠positive, OOD→review), showcase regression |
| 19–20 | Benchmark + report | real runs on real splits; honest report with limitations; final status with explicit NOT IMPLEMENTED list |

## Dataset acquisition policy

Never auto-download. `cli.genoguide data download <name>` is explicit; every
dataset records source URL, version, license, citation, download date, SHA-256.
Not committed to git. Items that cannot be fetched non-interactively:

- **SpliceAI scores** — Illumina/BaseSpace registration required → connector + docs only.
- **CADD full files** — ~80 GB per build → connector + docs only.
- **gnomAD sites VCFs** — TB-scale → NOT INTEGRATED as raw; constraint metrics
  (gene-level) integrated; per-variant AF left as connector (VEP plugin or API).
- **AlphaMissense** — public (CC BY-NC-SA 4.0), 600 MB+ → download script provided;
  fetched only when explicitly requested.
- **OMIM / DisGeNET / GeneReviews** — licensing → optional connectors only.

## Backward compatibility

- Legacy demo endpoints stay mounted; frontend keeps working against them.
- Legacy demo dataset/model remain available (labeled SYNTHETIC/DEMO) until the
  research path fully supersedes them; the demo `analyze` flow is regression-tested.

## Commit discipline

One commit per phase (or coherent phase group), tests run before each commit.
