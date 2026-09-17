# Clinical logic (non-negotiable)

GenoGuide is decision support, not a medical device. These rules are enforced in
code and tests (`tests/test_safety.py`, `tests/test_platform_*.py`).

1. **Unknown ≠ benign.** Empty ACMG inputs classify as VUS; criteria are `NOT_EVALUABLE`, never MET.
2. **ML probability ≠ ACMG classification.** `reconciliation.final_classification` is always ACMG.
3. **Phenotype similarity ≠ pathogenicity.** Phenotype ranking never writes ACMG criteria.
4. **Literature existence ≠ pathogenic evidence.** Radar records literature only if a real source payload is supplied.
5. **Prediction tools ≠ independent ACMG evidence automatically.** AlphaMissense / REVEL / CADD / SpliceAI are `UNCERTAIN` computational items in the radar, not auto-PS3/PP3 upgrades.
6. **Conflicting evidence remains conflicting.** Radar `CONFLICTING` caps confidence; it never becomes certainty.
7. **Missing evidence remains missing.** Absent sources are `MISSING`, never benign support.
8. **Phase is not inferred.** Inheritance solver returns `phase_status=UNKNOWN` without parental genotypes.
9. **A VUS is not a treatment recommendation.** Therapy ranking is a separate advisory connector.
10. **AI does not prescribe treatment.** The explanation engine sets `prescribes_treatment: false` and uses no LLM.
11. **Final interpretation is human-reviewable.** Curation states: AI_DRAFT → LAB_REVIEW → CLINICAL_REVIEW → FINALIZED / REJECTED / SUPERSEDED.
12. **Simulated ACMG never overwrites official interpretation.** `POST /api/v1/acmg/simulate` stores `official=0`.
13. **New evidence creates a new interpretation version.** History is append-only; finalized rows are not mutated in place.

OOD high, or high ML confidence with ACMG discordance, escalates `human_review_required`.
Reanalysis never auto-finalizes or silently rewrites a `FINALIZED` classification.
