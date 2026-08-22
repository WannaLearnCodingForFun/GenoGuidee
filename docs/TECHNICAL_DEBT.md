# GenoGuide — Technical Debt Register

Ordered by severity for a research-grade migration. Every item below is
verified against the code, not speculation.

## SEVERE (blocks any research claim)

1. **Label/feature circularity in ML training.** Training rows are produced by
   the same class-conditioned sampler as the demo cohort — the model learns the
   generator, not biology. The 0.94 accuracy is meaningless outside pipeline
   validation. *Fix: ClinVar-labeled training set with leakage-safe splits.*
2. **No real variant ingestion.** No VCF parsing, no normalization, no HGVS
   handling, no genome-build awareness. All variants are pre-fabricated dicts.
   *Fix: canonical variant schema + VCF validate/normalize + annotation layer.*
3. **No evaluation discipline.** Single random synthetic holdout; no
   gene-disjoint / chromosome / temporal splits; no leakage audit; no
   calibration or uncertainty; accuracy is the only metric.
4. **ESM-2 in demo mode is not an embedding.** Deterministic seeded vectors
   (honestly labeled), and live mode runs on synthetic sequence windows because
   no transcript/protein sequence source exists in the repo.

## HIGH

5. **ACMG engine is a 13/28 subset with global thresholds.** No ClinGen
   gene-specific specifications, no PVS1 decision tree, no PM5/PS4/PM3/BP1/PP2
   (gene-level mechanism knowledge absent), no per-criterion rule versioning.
   One non-standard combining shortcut: single BS → Likely Benign.
6. **PP3 / ML circularity.** Both "independent" paths consume the same
   in-silico scores (REVEL/CADD/SpliceAI); concordance is partially built-in.
7. **Consent recorded but not enforced.** `/api/analyze` never calls
   `verify_consent()` before running or recording.
8. **`patient_hash = SHA256("genoguide-patient|" + id)`** — unsalted hash of a
   low-entropy ID; trivially dictionary-attackable. Needs keyed HMAC with an
   off-ledger key.
9. **No tests of any kind** prior to this migration.

## MEDIUM

10. **Provenance metadata is thin.** No input hash, no annotation/KG/rule
    versions, no operator, no evidence snapshot; "reproducibility" is a claim,
    not a recorded artifact.
11. **All routes in one `main.py`;** no versioned API (`/api/...` unversioned),
    no role/authorization primitives, no job model for long-running work.
12. **In-memory dataset**: variants/patients are Python constants; no database
    beyond the ledger; `data/variants.json` is a dump, not a source of truth.
13. **No model/experiment registry.** The XGBoost JSON has no recorded
    dataset version, seed, git commit, metrics, or checksum.
14. **Relevance score weights are invented** (40/25/15/10/10 with class
    dampening). Defensible as UX, undocumented as science.
15. **Knowledge graph is per-patient and ephemeral** — rebuilt per request from
    demo constants; no ontology grounding (no MONDO/HPO IDs beyond labels).

## LOW

16. `_dump` of variants.json happens at import time (side effect on import).
17. `combine()` in `acmg.py` marks `likely_benign` via a non-standard rule.
18. No `.gitignore` (fixed in this migration); runtime DB was committed.
19. `esm_status()` reports `ready: true` even when nothing is loaded (demo
    semantics; must be explicit in v1 API).
20. Overview "variants analyzed" (74,305) is a sum of narrative constants —
    fine for demo, must never leak into research reporting.
