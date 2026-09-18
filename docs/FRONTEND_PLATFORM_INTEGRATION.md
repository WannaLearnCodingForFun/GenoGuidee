# Frontend platform integration

**Date:** 2026-09-17  
**Constraint:** additive only. Legacy App Router pages stay.

## Existing routes

| Route | File |
|---|---|
| `/` | `(marketing)/page.tsx` |
| `/login` `/signup/*` | `(auth)/` |
| `/dashboard` | `(app)/dashboard/page.tsx` |
| `/clinical-workup` | `(app)/clinical-workup/page.tsx` |
| `/variant-lab` | `(app)/variant-lab/page.tsx` |
| `/patient-context` | `(app)/patient-context/page.tsx` |
| `/genomic-timeline` | `(app)/genomic-timeline/` |
| `/therapy` | `(app)/therapy/page.tsx` |
| `/knowledge-graph` | `(app)/knowledge-graph/page.tsx` |
| `/provenance` | `(app)/provenance/page.tsx` |
| `/model-evaluation` | `(app)/model-evaluation/page.tsx` |
| `/upload` | `(app)/upload/page.tsx` |
| `/unauthorized` | `unauthorized/page.tsx` |

Shell: `(app)/layout.tsx` = `AuthGate` + `Sidebar` + `main.pl-60`.

## Existing components

`Sidebar`, `AuthGate`, `SystemStatus`, `WorkupStages`, `WorkupResultCard`, marketing chrome, `DnaHelix`.  
No shared Button/Badge/Dialog package — pages use Tailwind `card`, `text-cyan`, `border-error/40`.

## Existing navigation

`frontend/src/lib/nav.ts` + `NAV_BY_ROLE` (doctor / patient / lab_technician).  
Icons in `Sidebar.tsx` keyed by **label**.

## Existing API client

Single client: `frontend/src/lib/api.ts` (`get` / `post` / `patch` / `api.*`).  
Auth: local bearer `genoguide_token` or Supabase session.  
No React Query / SWR.

## Design system

Geist + Geist Mono. Light theme: navy `#181a2f`, crimson `#b4182d` (`text-cyan`).  
`.card`, `classColor` / `levelColor` in `lib/ui.ts`. Framer Motion. Recharts. Lucide.  
Knowledge graph is a custom SVG force layout — reuse that, not a new viz library.

## New backend endpoints (source of truth: `backend/app/api/platform.py`)

| Frontend page | APIs |
|---|---|
| `/evidence-intelligence` | `POST /api/v1/evidence/radar`, `GET /api/v1/graph?seed=`, `POST /api/v1/evidence/graph/edge`, `GET /api/variants`, `POST /api/analyze` |
| `/reanalysis` | `POST /api/v1/reanalysis/check`, `/run`, `GET /jobs/{id}`, `/changes`, watchlist |
| `/interpretations/[id]` | `GET /api/v1/interpretations/{id}/history`, `/diff/{a}/{b}` |
| `/curation` | `POST /api/v1/curation`, `GET /api/v1/curation/{id}/events` |
| `/phenotype-analysis` | `POST /api/v1/phenotypes/normalize\|match\|rank-genes\|rank-diseases` |
| `/inheritance` | `POST /api/v1/inheritance/solve` |
| `/acmg-simulator` | `POST /api/v1/acmg/simulate`, `POST /api/v1/acmg/evaluate` |
| `/phenopackets` | `POST /api/v1/phenopackets/import`, `GET /api/v1/cases/{id}/phenopacket` |
| `/model-monitoring` | `GET/POST /api/v1/model-monitoring`, `/ood` |

Errors: `{error:{code,message,request_id}}` (not FastAPI `detail`).

## New frontend routes

```
/evidence-intelligence
/reanalysis
/curation
/phenotype-analysis
/inheritance
/acmg-simulator
/phenopackets
/model-monitoring
/interpretations/[id]
```

## Role requirements

Frontend roles remain `doctor | patient | lab_technician`.  
Platform nav: **doctor + lab_technician only**. Patients keep legacy pages.  
Curation finalize: backend 403 for PATIENT even if UI hid the button.  
Mapped `X-Role`: doctor→DOCTOR, lab_technician→LAB_CLINICIAN, patient→PATIENT.

## Shared new components

`frontend/src/components/platform/*` — radar, graph, tables, diff, queues, simulator panels.  
Client: `frontend/src/lib/platform/`.

## Compatibility risks

- Sidebar length → scroll the nav, do not replace the shell.
- Do not rename `/knowledge-graph` or `/provenance`.
- `api.ts` `GraphNode` is the **legacy** clinical graph; platform graph uses different keys (`source_key` / `node_key`).
- `model-evaluation/page.tsx` TypeScript `unknown` ReactNode issue is fixed with an explicit display string.
- Lint errors in `AuthGate` / `useAccount` (`setState` in effect) are pre-existing; not rewritten.
- Feature flag `NEXT_PUBLIC_ENABLE_PLATFORM_FEATURES=false` hides platform nav; legacy routes unchanged.
