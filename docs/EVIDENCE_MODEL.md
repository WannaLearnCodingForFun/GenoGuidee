# Evidence model

Typed evidence graph (`backend/app/platform/evidence_graph.py`).

## Nodes

Patient, Case, Variant, Gene, Transcript, Protein, Disease, Phenotype, Evidence,
Publication, ClinVarAssertion, ClinGenAssertion, PopulationObservation,
FunctionalStudy, Guideline, Drug, Interpretation, Reviewer.

## Edges

Includes `VARIANT_HAS_EVIDENCE`, `EVIDENCE_SUPPORTS_CRITERION`,
`EVIDENCE_CONTRADICTS_CRITERION`, `VARIANT_HAS_CLINVAR_ASSERTION`,
`INTERPRETATION_USES_EVIDENCE`, plus structural edges (`VARIANT_IN_GENE`, …).

## Provenance (mandatory on evidence edges)

Every evidence edge must include:

```json
{
  "source": "ClinVar",
  "source_id": "VCV…",
  "source_version": "2026-08",
  "retrieved_at": "2026-09-17T00:00:00+00:00",
  "evidence_strength": "EXPERT_PANEL",
  "direction": "SUPPORTS_PATHOGENIC"
}
```

The API returns `EVIDENCE_PROVENANCE_REQUIRED` if `source` or `retrieved_at` is omitted.

## Conflict radar

`POST /api/v1/evidence/radar` aggregates ClinVar, ClinGen, gnomAD, computational
scores, functional/literature (when provided), ACMG, ML, and phenotype.

States: `CONCORDANT | MIXED | CONFLICTING | INSUFFICIENT`.

Categories: `PATHOGENIC_SUPPORT | BENIGN_SUPPORT | UNCERTAIN | CONFLICTING | MISSING`.

Missing is never converted to benign. Conflict is never converted to confidence.

## Explanations

`POST /api/v1/evidence/explain` emits claims with `evidence_ids` only. No LLM.
Insufficient ACMG → `INSUFFICIENT EVIDENCE FOR AUTOMATED EXPLANATION`.
