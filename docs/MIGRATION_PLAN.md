# GenoGuide — Migration Plan (status)

The demo → research migration has been executed in-tree **without modifying `frontend/`**. This document is the living status against the original 20-phase plan.

| Phase | Status | Notes |
|---|---|---|
| 1 Audit | DONE | `docs/CURRENT_ARCHITECTURE.md` |
| 2 Canonical schema + acquisition | DONE | `CanonicalVariant`; `research/data/manifest.yaml`; CLI `data list/download/verify` |
| 3 VCF validate/normalize | DONE | pure-Python + bcftools if present; no silent left-align claim |
| 4 Evidence integration | PARTIAL | ClinVar, constraint, ClinGen, HPO real. AM optional. REVEL/SpliceAI/CADD/gnomAD-sites = connectors |
| 5 Training dataset | DONE | parquet builder + quality report |
| 6 Leakage-safe splits | DONE | random / gene / chrom / temporal / expert; `leakage.assert_no_severe_leakage` |
| 7 Baselines | PARTIAL | LogReg + XGBoost trained on ClinVar. RF/LGBM/MLP implemented, not in last recorded run |
| 8 ESM-2 | INTERFACE | `research/training/esm_representation.py` — frozen extractor; not in production interpret path |
| 9 Multimodal | INTERFACE | fusion hooks documented; no trained multimodal weights |
| 10 Calibration + OOD | DONE | temperature scaling; Mahalanobis OOD; entropy/max-prob |
| 11 ACMG v2 | DONE | 28 criteria + ClinGen YAML layer + strict combining |
| 12 Phenotype | DONE | HPO IC, Resnik/Lin/Jaccard; does not alter ACMG |
| 13 Knowledge graph | DONE | NetworkX; Neo4j extension point |
| 14 Clinical evidence | DONE | considerations with sources; safety gate |
| 15 Provenance v2 | DONE | hashes + versions; no genomic payload |
| 16 FastAPI v1 | DONE | mounted alongside legacy `/api/*` |
| 17 CLI | DONE | `python -m cli.genoguide …` |
| 18 Tests | DONE | pytest unit / safety / API / showcase |
| 19 Benchmark | PARTIAL | gene-disjoint real numbers recorded; `--all` splits depend on local parquet |
| 20 Research report | DONE | `research/reports/final_model_report.md`, model/data cards |

## Backward compatibility

- Legacy `/api/*` untouched in contract.
- New work under `/api/v1/` and CLI.
- Synthetic demo data remains labeled SYNTHETIC/DEMO.

## Next (not blocking CLI/tests)

1. Install lightgbm and re-run full model list.
2. User-provided VEP cache + gnomAD sites tabix for real AF.
3. Protein FASTA (UniProt/MANE) → ESM-2 delta features → retrain with/without ESM ablation.
4. Official ClinGen VCEP YAML files (status: OFFICIAL) replacing TEMPLATEs.
5. Real auth replacing `X-Role`.
