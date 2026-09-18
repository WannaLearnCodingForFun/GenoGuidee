# Frontend baseline (before platform UI)

**Date:** 2026-09-17  
**Branch:** `main` (ahead of `genoguidee/main` by 2 backend commits)  
**Package manager:** npm (`frontend/package.json`)

## Commands

```bash
git status
git branch
cd frontend && npm run lint
cd frontend && npm run build
```

`npm test` is **not configured** (no test runner / no `*.test.tsx` files).

## git

Working tree still contains uncommitted longitudinal / genomic-timeline / model-evaluation WIP. Platform UI must not discard those files.

## lint (`npm run lint`)

**Fail (pre-existing).** 12 errors / 7 warnings. Notable:

- `AuthGate.tsx` — `setMounted(true)` in effect (`react-hooks/set-state-in-effect`)
- `useAccount.ts` — `setLoading(false)` in effect
- `window.location.href` warning on marketing/login

These are not introduced by platform pages. They are **not** fixed in this change (would rewrite auth).

## build (`npm run build`)

Compile succeeds. Typecheck **fails**:

```
src/app/(app)/model-evaluation/page.tsx(157,90):
Type 'unknown' is not assignable to type 'ReactNode'.
```

Untracked WIP page. Must be fixed with a one-line type annotation so the final platform build can pass. Not a redesign.

## Final platform UI check (after implementation)

```
cd frontend && npm test     # PASS (scripts/check-platform.mjs)
cd frontend && npm run build  # PASS
pytest tests/test_frontend_platform_routes.py  # PASS
```

`npm run lint` still fails on pre-existing AuthGate / useAccount `setState` in effect. New platform files lint clean.

Live backend: `/docs` 200, radar/reanalysis/monitoring/simulate/inheritance match schemas.
Unauthenticated platform routes 307 → `/login`. Authenticated doctor 200 on legacy + new routes.
TP53 showcase: ACMG VUS vs ML Likely Pathogenic, DISCORDANT.
Patient finalize curation: 403 FORBIDDEN.

