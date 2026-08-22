# GenoGuide — Current Architecture

**Audit date:** 2026-08-22 (post research-engine migration + optional therapy connector)
**Scope:** entire repository. Legacy `/api/*` remains frozen. `frontend/` gained an additive `/therapy` page; Variant Lab / Patient Context / PGx were not rewritten.

**Verdict:** two stacked systems coexist.

1. **Legacy demo API** (`/api/*`) — original hackathon surface. Synthetic dataset, 13-criterion ACMG v1, demo XGBoost, hash-chained SQLite ledger v1. **Preserved unchanged** so the independently redesigned frontend keeps working.
2. **Research engine** (`/api/v1/*`, `cli/`, `research/`) — ClinVar-labeled training, leakage-safe splits, ACMG/AMP 2015 28-criterion engine, HPO phenotype matching, NetworkX knowledge graph, provenance ledger v2, terminal-first CLI.

---

## 1. Repository layout

```
sih/
├── frontend/                      READ-ONLY. Next.js demo UI. Do not modify.
├── backend/app/
│   ├── main.py                    Legacy /api/* + mounts /api/v1
│   ├── api/v1.py                  Versioned research API
│   ├── schemas/{variant,interpretation}.py
│   ├── bioinformatics/{vcf,pipelines}.py
│   ├── interpretation/{acmg_v2,clingen_specs,reconcile,clinical_v2}.py
│   ├── phenotype/{ontology,similarity,family}.py
│   ├── knowledge_graph/graph.py
│   ├── provenance.py              ledger v1 (demo)
│   ├── provenance2/ledger.py      ledger v2 (research)
│   ├── services/{evidence,interpret,drug_recommendation}.py
│   ├── dataset.py / ml.py / acmg.py / clinical.py   demo (SYNTHETIC)
│   └── model_store/               demo XGBoost artifact
├── research/
│   ├── data/{manifest.yaml, raw/, interim/, processed/}   raw data git-ignored
│   ├── acquisition.py
│   ├── preprocessing/             ClinVar → parquet, gene features, AF, training matrix
│   ├── training/                  baselines, calibration, uncertainty, registry, ESM interface
│   ├── evaluation/{splits,metrics,leakage}.py
│   ├── reports/                   real benchmark JSON/MD (gene-disjoint run recorded)
│   └── experiments/
├── models/{registry,production}/
├── cli/                           python -m cli.genoguide …
├── configs/{model.yaml, clingen/}
├── tests/                         pytest
└── docs/
```

## 2. Legacy demo API (preserved)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/status`, `/api/stats` | demo stats |
| GET | `/api/variants`, `/api/variants/{id}` | 120 in-memory variants |
| POST | `/api/analyze` | ESM-demo + XGBoost + ACMG v1 + ledger v1 |
| GET | `/api/patients*`, `/api/graph/{id}` | synthetic patients |
| GET/POST | `/api/provenance/*` | ledger v1 |

ML never overrides ACMG in this path (`final_classification = acmg["classification"]`).

## 3. Research API (`/api/v1`)

Health, variant normalize/annotate, interpret, ACMG evaluate/rules, phenotype match/rank, gene graph, provenance verify/audit, research datasets/models/benchmarks, **optional** `POST /api/v1/therapy/recommend` (somatic oncology ranking; default off). Role primitives via `X-Role` header (architecture only — not production auth).

## 4. ML (research)

- **Trained:** logistic regression and XGBoost on a ClinVar-derived 5-class tabular matrix (consequence one-hots, gene constraint, ClinGen validity, AlphaMissense when present, log AF when present). Temperature calibration on validation only. Mahalanobis OOD.
- **Headline split:** gene-disjoint. Random split exists and is **not** used for model selection.
- **Recorded result (real run):** gene-disjoint test, n=120,000 sampled from held-out genes. Best model by primary AUPRC: **logreg** (macro AUPRC 0.572, AUROC 0.898, MCC 0.610). XGBoost close (AUPRC 0.558). Binary pathogenic-vs-benign AUPRC ~0.937.
- **NOT IMPLEMENTED as trained artifacts:** LightGBM/RF/MLP (code exists in `train_baselines.py`; last recorded experiment trained logreg+xgboost only), ESM-2 live embeddings, multimodal fusion, stacked ensemble. Interfaces exist; training those requires torch/fair-esm and/or a protein sequence source.
- **Demo XGBoost** in `backend/app/ml.py` remains synthetic-trained and is **not** the research model.

## 5. ACMG v2

All 28 Richards 2015 criteria as independent evaluators. Missing inputs → `NOT_EVALUABLE` (never MET). PP5/BP6 disabled by default (ClinGen/Biesecker 2018). Combining rules follow Table 5 strictly (conflicting path+benign → VUS). ClinGen YAML specification layer (`configs/clingen/`) with TEMPLATE vs OFFICIAL status.

## 6. Data

Manifest-driven acquisition. Never silent download. Raw data git-ignored.

| Source | State |
|---|---|
| ClinVar variant_summary + GRCh38 VCF | downloadable; processed parquet used for labels/PS1/PM5 |
| HPO (obo, hpoa, genes_to_phenotype) | downloadable; phenotype engine |
| gnomAD v4.1 constraint | downloadable; gene features |
| ClinGen gene-validity | downloadable; KG + gene features |
| AlphaMissense hg38 | downloadable (CC BY-NC-SA); optional feature |
| REVEL / SpliceAI / CADD / gnomAD sites | connectors; auto_downloadable false or not configured |

## 7. Provenance

- v1: demo SQLite chain (`provenance.py`) — hashes of interpretation payloads.
- v2: `ledger_v2` with input/output hashes, annotation/model/ACMG/KG/phenotype versions, evidence snapshot hash, operator. Genomic sequence never stored.

## 8. Tests

`pytest` under `tests/`: schema, VCF, ACMG safety, reconciliation safety, splits, family, API v1, legacy showcase regression.

## 9. Explicit NOT IMPLEMENTED

- Offline Ensembl VEP (no cache; annotation from ClinVar + gene features)
- True left-alignment without bcftools+FASTA
- DeepVariant/GATK execution (wrappers only; tools typically not installed)
- Fine-tuned ESM-2 / LoRA / multimodal neural net / stacked meta-learner (code hooks only)
- Neo4j (NetworkX research graph)
- Hyperledger Fabric (local hash chain)
- Real authentication/OIDC
- LLM layer (deliberately omitted)
- OMIM / GeneReviews / DisGeNET / PharmGKB (license)
- Somatic *classification* logic (ACMG/AMP is germline). An optional **therapy ranking connector** exists (`drug_recommendation.py`) and does not classify variants.
- CNV/SV interpretation
