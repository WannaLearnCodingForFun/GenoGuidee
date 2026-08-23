# Longitudinal model

## What exists

`variant_observations` records one row per real uploaded sample × variant.

`GET /api/clinical/patients/{id}/longitudinal` groups by variant key.

- 0 observations: no data
- 1 sample: `Single observation — longitudinal trajectory unavailable.`
- ≥2 real files/timepoints: plot the stored dates and VAF values only

No interpolation. No invented historical points. One VCF is never expanded into a fake timeline.

## Outcome / survival

**Not implemented.** There is no licensed longitudinal outcome cohort in this repo with time-to-event labels that would justify Cox / RSF / death timing.

The API always returns:

`No validated outcome prediction available.`

Never display “death in X months.”
