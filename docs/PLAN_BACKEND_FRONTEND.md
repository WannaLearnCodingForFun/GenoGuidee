# GenoGuide — Backend + Frontend Plan

**Status:** PLANNING ONLY. Nothing in this document has been executed. Every phase
below is a paste-ready prompt for a Claude Code session (this one or a sub-agent on
another machine) to pick up one at a time.

**Basis:** this plan is grounded in an actual audit of the current repo
(`/home/Kunsh/Projects/SIH/GenoGuide`) run 2026-08-22, not the aspirational
monorepo/orchestrator architecture sketched in an earlier planning conversation. Where
that earlier sketch's ideas are still worth keeping, they're folded in below and
marked. Where they assume infrastructure (pgmq, packages/contracts codegen,
services/orchestrator) this repo doesn't have and doesn't need yet, they're deferred
to §5 with a reason, not silently dropped.

---

## 0. Reality check — correcting the premise

Two claims motivated this plan. Both are only half true:

1. **"The frontend is like a PPT."** False for data-fetching: every page under
   `frontend/src/app/(app)/` calls a real endpoint (FastAPI `:8000` via `lib/api.ts`,
   or Supabase directly for `upload/`). No page renders a hardcoded array or a dead
   button. **What's actually true:** the dashboard is a near-empty hero with no
   widgets, and — more importantly — **every role sees an identical sidebar and can
   reach every page.** A patient account can open Provenance, Therapy Ranking, and
   Variant Lab exactly like a doctor. That's the "PPT" feeling: a real product with
   no product-shaped access control.

2. **"ML models aren't ready."** Partly true, partly not, and the scope changed
   mid-plan. A trained pathogenicity classifier (logreg/xgboost on ClinVar) does
   exist in `models/production/*.joblib` with a real recorded benchmark — but
   **it is dropped from production scope at your instruction**, because the
   training-scale data it depends on (bulk ClinVar + gnomAD v4 constraint) is
   not publicly accessible to this team going forward. See
   `docs/PLAN_ML_MODELS.md` §0 and §3. Do not wire those artifacts into any new
   work under this plan.

   What remains, and is real:
   - **ACMG v2** — the deterministic 28-criterion rule engine
     (`interpretation/acmg_v2.py`) — not a trained model, doesn't share the
     dropped classifier's data problem for its own logic (though its evidence
     sources, ClinVar/gnomAD lookups, may partially overlap — confirmed as an
     open decision in the ML plan §4.1). This remains the sole classification
     authority.
   - **Drug/therapy ranker** (Gradient Boosting on real CIViC + DGIdb data) —
     `Medical_DrugRecommendation/model/model.pkl`, wired in by default as a
     local in-process engine (`services/drug_recommendation.py`).
   - **Cohort/nearest-mutation similarity matcher** — new build (ML Plan
     Model 2), reusing existing HPO similarity code, now the system's primary
     instance-based evidence source in place of a supervised classifier.

   **What's actually missing** on the backend/frontend side is the glue: ACMG v2
   isn't reliably in the authenticated request path yet (the legacy demo path
   uses a separate synthetic XGBoost, unrelated to any of the above), and
   there's no gate deciding when therapy ranking is even allowed to run.

3. **The Supabase auth/RLS schema you asked about ("three forms, three tables, all
   linked") already exists** — `frontend/supabase/migrations/20260822105209_init_roles_schema.sql`
   defines `profiles` → `doctors` / `patients` / `lab_technicians`, linked via
   `patients.primary_doctor_id` and the `lab_orders` join table, with RLS on every
   table. What's missing is (a) three separate signup forms instead of one toggle
   form, (b) a human-readable unique reference ID on `doctors` and `lab_technicians`
   (patients already have one: `mrn`), and (c) that Supabase identity never reaches
   the FastAPI backend — see Phase B1.

---

## 1. Architecture decision

**Keep the current stack as-is:** Next.js (App Router, BFF-ish route handlers) +
Supabase (auth, RLS, Postgres, storage) + Python FastAPI (`:8000`) reached over
ngrok in dev. Do **not** adopt a pgmq/orchestrator worker, a `packages/contracts`
codegen pipeline, or a services/ monorepo split at this stage.

**Why not:** that architecture is the right answer at a scale this project isn't at
yet — one backend, one frontend, a handful of sub-agents. Introducing a queue worker,
generated-contract CI gates, and a multi-service network adds real operational
surface (a worker process to keep alive, a codegen step that can drift, a private
network to configure) for a system that currently has three total ML-relevant
endpoints in the hot path. Revisit this decision at Phase 3 (§5) once there's a
concrete reason (e.g. interpretation requests routinely exceed the request-handler
timeout, or two people are actively editing the same schema and hitting drift).

**What's kept from the elaborate sketch because it's cheap and correct regardless of
scale:**
- PHI never crosses into the ML-services boundary (already true — `deid`-style
  handling already exists informally; formalize in Phase B4/B5).
- Therapy ranking is gated behind classification + sign-off, never called
  unconditionally (Phase B5 — currently not enforced anywhere in this repo).
- Every ML-derived output shows its basis (already true for ACMG; extend to therapy).

---

## 2. Phases

Each phase is a self-contained prompt. Paste one at a time into a Claude Code
session. Do not paste the whole plan and ask for "the project."

### Phase B0 — Three role forms + reference IDs

```
Read frontend/supabase/migrations/20260822105209_init_roles_schema.sql and
frontend/src/app/(auth)/signup/page.tsx.

1. Migration (new file, forward-only, never edit the applied one): add a unique
   text column `reference_id` to `public.doctors` and `public.lab_technicians`,
   generated at signup time as 'DOC-' || upper(substr(id::text,1,8)) and
   'LAB-' || upper(substr(id::text,1,8)) respectively — same pattern already used
   for patients.mrn in private.handle_new_user(). Patients keep `mrn` as their
   reference id (do not add a redundant column). Update
   private.handle_new_user() to set it. Add a unique index.

2. Frontend: replace the single toggle-based signup form with three separate
   routes/pages: /signup/doctor, /signup/patient, /signup/lab-technician, each
   showing only that role's fields. Factor the shared bits (name/email/password,
   supabase signUp call, "check your email" state) into one small shared
   component so the three pages aren't full copies — but keep them as three
   distinct entry points/routes, not one form with a role switch. Turn the root
   /signup page into a role picker linking to the three.

3. Show the generated reference_id back to the user after signup confirmation
   (e.g. "Your doctor reference ID is DOC-A1B2C3D4 — keep it for your records").

Acceptance: three distinct signup URLs exist; each creates a profile + role-detail
row with a unique reference_id; existing RLS policies untouched; `npm run build`
passes; manually sign up one of each role against the linked Supabase project and
confirm all three rows (profiles + role table) appear with the FK to auth.users
intact.
```

### Phase B1 — Bridge Supabase identity into the FastAPI backend

```
Read backend/app/main.py, backend/app/api/v1.py, frontend/src/lib/api.ts, and
frontend/src/app/(app)/variant-lab/page.tsx (note the hardcoded
patient_id: "G-1027" fallback — this is the concrete symptom of the gap).

Currently the FastAPI backend has zero knowledge of the Supabase session: no JWT
is ever forwarded from the frontend, so every backend call operates on synthetic
demo data (120 variants, 3 patients) regardless of who's logged in.

1. On the FastAPI side: add a dependency that verifies a Supabase-issued JWT
   (passed as Authorization: Bearer <token>) against the project's JWT secret
   (env var, never hardcoded), extracting `sub` (the Supabase user id) and
   looking up role via a service-role Supabase client call to `profiles`.
   Reject with 401 if missing/invalid. Do NOT trust a client-supplied role
   header for anything beyond UI hints (X-Role stays architecture-only per
   docs/TECHNICAL_DEBT.md item 10 — do not upgrade it to real auth silently;
   that's this phase's actual job for the new dependency, so retire the old
   header's authority once this lands).

2. On the frontend side: `lib/api.ts` must attach the current Supabase session's
   access token to every backend call. Add a helper that reads the session via
   `createClient()` and sets the Authorization header.

3. Remove the hardcoded "G-1027" in variant-lab/page.tsx; the patient context
   must come from the authenticated user's own Supabase patient row (or, for a
   doctor, a patient they're allowed to see per RLS / care-team relationship).

4. Do not change what data is returned yet (still synthetic dataset is fine for
   this phase) — this phase is only about the identity plumbing being correct
   and enforced, so Phase B3 has something real to attach to.

Acceptance: an authenticated request without a valid Supabase JWT gets 401 from
every backend route that touches patient data; a valid doctor JWT resolves to
that doctor's role server-side (not client-asserted); no hardcoded patient id
remains in the frontend; a test proves a tampered/expired JWT is rejected.
```

### Phase B2 — Role-based navigation and route guards

```
Read frontend/src/components/Sidebar.tsx and frontend/src/lib/supabase/proxy.ts
(the middleware).

Currently NAV is one flat array shown identically to doctor, patient, and
lab_technician accounts (Sidebar.tsx ~line 26). A patient can reach every
clinician-facing page.

1. Define, per role, which of the existing pages are visible:
   doctor: dashboard, clinical-workup, variant-lab, patient-context, therapy,
     knowledge-graph, provenance, upload
   patient: dashboard, upload, provenance (their own), and a read-only view of
     their own interpretation status — NOT variant-lab, NOT therapy ranking
     (raw classifications/drug rankings should not go to patients unmediated —
     this mirrors a real clinical-safety norm, not just a nav preference; ask
     me before changing it)
   lab_technician: dashboard, upload, and only lab_orders assigned to them —
     NOT clinical-workup, NOT therapy
   Confirm this breakdown with me before implementing if anything is unclear —
   don't guess at what a lab technician should or shouldn't see.

2. Filter Sidebar's NAV by `account.role`.

3. Add a server-side guard (in the proxy/middleware or a layout) that 403s /
   redirects on direct navigation to a route the role can't see — client-side
   nav filtering alone is not access control.

Acceptance: each of the three roles, logged in, sees only its allowed nav items;
directly hitting a disallowed URL (e.g. a patient hitting /therapy) redirects or
403s server-side, not just hides the link.
```

### Phase B3 — Wire ACMG v2 (not the dropped classifier) into the authenticated path

```
Read backend/app/api/v1.py's /interpret route, backend/app/ml.py (the demo
path), backend/app/interpretation/acmg_v2.py, and backend/app/services/
drug_recommendation.py.

Note the scope change: the previously-planned supervised pathogenicity
classifier (models/production/*.joblib) is DROPPED from production — its
training-scale data access is gone (see docs/PLAN_ML_MODELS.md §0, §3). Do not
wire those artifacts in. Classification authority is ACMG v2
(interpretation/acmg_v2.py, real 28-criterion deterministic engine) alone —
it was never dependent on the dropped classifier and doesn't need "ML" wired
in at all for this phase.

Currently the legacy /api/analyze path — which is what a logged-in user's
"Clinical Workup" and "Variant Lab" pages actually call per lib/api.ts — runs
ACMG v1 (13-criterion, per docs/CURRENT_ARCHITECTURE.md) plus a
synthetic-trained demo XGBoost, not ACMG v2.

1. Report back first: confirm exactly which endpoints the authenticated
   frontend pages call (api.workup, api.analyze) and which ACMG engine version
   (v1 in main.py vs v2 in api/v1.py) each actually runs. Do not assume — read
   the code.

2. Once confirmed, make the authenticated, real-patient-data path (post Phase
   B1) run ACMG v2 as the classification authority, while leaving the
   pre-existing legacy /api/analyze demo path (ACMG v1 + demo XGBoost) frozen
   and labeled as demo (per the "Legacy demo API preserved unchanged"
   invariant in docs/CURRENT_ARCHITECTURE.md) for the existing synthetic
   showcase.

3. The demo XGBoost's classification must never override ACMG's — this
   invariant already holds in the demo path (reconciliation.final_
   classification = ACMG) and must hold in the real path too, even though
   there is no supervised classifier to reconcile against here (ACMG v2 is
   simply authoritative on its own). Add a test asserting no code path lets
   anything override ACMG v2's output.

4. Once the cohort similarity matcher (ML Plan, Model 2) has an endpoint, wire
   its output alongside ACMG v2's in the interpretation response as
   supporting evidence — clearly labeled as case-based similarity, not a
   classification. Do not block this phase on that endpoint existing yet;
   land ACMG v2 wiring first and treat the similarity-matcher hookup as a
   small follow-up once /api/v1/similar-cases exists.

Acceptance: a real authenticated interpretation request runs ACMG v2, not
ACMG v1 + demo XGBoost; a test proves nothing can override ACMG v2's
classification; the legacy demo path is unchanged (existing tests still pass).
```

### Phase B4 — Variant normalization bridge (ACMG v2 output → therapy ranker input)

```
Read backend/app/schemas/variant.py, backend/app/services/drug_recommendation.py
(note the _HGVS3 / _BARE / _UNMAPPABLE regexes — there is already a partial,
regex-based normalizer here, not nothing) and Medical_DrugRecommendation/
preprocessing/normalizer.py.

ACMG v2's variant intake emits genomic coordinates / HGVS / consequence terms.
The therapy ranker wants {gene, protein_short like "L858R", disease}. Right now
the bridge is a set of regexes in drug_recommendation.py that can parse a
missense HGVS but has no explicit "this variant has no protein-shorthand form"
branch for frameshift/splice/CNV — those currently either fail the regex
silently or produce a wrong/partial mapping. Confirm this by reading the
existing UNMAPPABLE handling before writing anything.

1. Add an explicit `therapy_addressable: bool` + `therapy_block_reason: str|None`
   result to the normalization step: true only for single-residue substitutions
   with a valid protein_short; false with a specific reason (frameshift, splice,
   CNV/SV, indel, unmappable) for everything else.

2. The therapy endpoint must check this flag before calling the ranker at all,
   returning a structured "not applicable to this variant type" response
   instead of attempting the call and getting a 422 from the ranker.

3. Unit tests: BRCA1 frameshift (GRCh38:17:43057062:T>TG) → therapy_addressable
   = false with reason; EGFR p.Leu858Arg → true, protein_short = "L858R".

Acceptance: no path exists where a non-substitution variant reaches the therapy
ranker; both test cases pass; the reason string is shown in the therapy UI
(Phase B7), not swallowed.
```

### Phase B5 — Therapy gate (pure function)

```
Read backend/app/services/drug_recommendation.py and the ACMG reconciliation
output shape in interpretation/acmg_v2.py / clinical.py.

There is currently no gate: any variant, any classification, can have therapy
ranking called on it. This is the single highest-risk gap carried over from the
earlier planning sketch, and it's real here too — verify by reading, not by
assuming the sketch's diagnosis transfers unchanged.

1. Write gate(final_classification, therapy_addressable, review_status) -> 
   {allow: bool, reason: str|None} as a pure function, no I/O, fully unit
   tested. Rules (confirm/adjust with me — this is a clinical rule, not an
   engineering default, per the "ask before inventing a clinical rule" norm):
   - allow only if final_classification in {pathogenic, likely_pathogenic}
   - never allow if therapy_addressable is false (Phase B4)
   - never allow if the interpretation hasn't been reviewed/signed off by a
     doctor (this requires a review_status concept — currently absent; smallest
     addition is a nullable reviewed_by/reviewed_at pair on wherever
     interpretations are persisted; propose the smallest schema change and
     confirm before migrating)

2. Wire the gate in front of the therapy endpoint. A gated response must be
   structurally distinct from "no recommendations found" (409 or an explicit
   {gated: true, gate_reason} shape) — collapsing the two into one empty
   response is the exact failure mode to avoid, since an empty list reads as
   "no treatment indicated" rather than "not evaluated yet."

Acceptance: exhaustive table-driven unit tests over the gate's input space;
an integration test proving a VUS or an unsigned-off pathogenic variant cannot
produce a ranked drug list through any endpoint.
```

### Phase B6 — Real dashboard content

```
Read frontend/src/app/(app)/dashboard/page.tsx.

Currently this is a near-empty hero. Post Phase B1 (real identity) and B0
(three role tables), build role-specific widgets:
 - doctor: their care-team patients (via patients.primary_doctor_id), any
   pending sign-offs (post Phase B5), recent interpretations
 - patient: their own upload status (vcf_uploads), their own interpretation
   status in plain language, not a raw classification
 - lab_technician: lab_orders assigned to them, by status

Acceptance: each role's dashboard shows real counts/rows from their own
Supabase-scoped data (RLS-enforced, not filtered client-side); empty states are
explicit ("no patients assigned yet"), not blank.
```

### Phase B7 — Audit logging

```
Add an append-only audit_log table (Supabase migration): actor_id, actor_role,
action, resource_type, resource_id, patient_id, at, detail jsonb. Revoke
update/delete from all roles including service_role's default grants beyond
insert/select as needed — this table must be genuinely append-only.

Log: every read of a patient's interpretation/therapy result by a doctor, every
sign-off, every gate override (there is no override path yet — if B5 doesn't
add one, don't log for it; only log real actions), every upload.

Acceptance: an RLS test proves no client role can UPDATE or DELETE a row in
audit_log; a manual walkthrough of "doctor views a patient's therapy result"
produces exactly one new audit_log row with the right actor/resource.
```

### Phase B8 — Test suite

```
- RLS access-matrix test: seed 2 doctors, 2 patients (one per doctor), 1 lab
  technician with one lab_order. Using real anon-key clients with real JWTs
  (not the service role), assert every cross-tenant read/write that should
  fail does fail, and every same-tenant one that should succeed does.
- PHI boundary test: assert the payload sent to Medical_DrugRecommendation /
  the ngrok therapy endpoint never contains patient_id, name, mrn, dob, email,
  or free text — only gene/variant/disease.
- Gate table test (Phase B5) and normalizer test (Phase B4), if not already
  written in those phases.

Acceptance: all of the above pass in CI; report any RLS gap found rather than
quietly patching around it if it reveals something not covered by the existing
migration.
```

### Phase B9 — Harden the ngrok path

```
Read backend/app/services/drug_recommendation.py's remote-call path.

The remote therapy engine, when GENOGUIDE_DRUG_API_URL is set, is reached over
a public ngrok URL with no shared-secret check found in the current code —
confirm this by reading before changing anything. If confirmed:

1. Add a required shared-secret header (e.g. X-GenoGuide-Key, env
   GENOGUIDE_TUNNEL_KEY) checked on both ends when the remote path is used.
2. Ensure request logging never logs the payload body (gene/variant/disease is
   low-sensitivity here, but keep the habit consistent with the PHI-boundary
   discipline elsewhere).

This does not apply to the local in-process engine path, which is the default
and doesn't cross a network boundary at all.

Acceptance: a request to the remote engine without the header is rejected by
the remote side; document the required env vars in README.
```

---

## 3. Explicitly deferred (not now, with reasons)

- **Supervised pathogenicity classifier in production.** Dropped, not deferred —
  see `docs/PLAN_ML_MODELS.md` §0/§3. The training-scale data it needs is not
  publicly accessible. `models/production/*.joblib` stays in the repo as a
  historical artifact only; no phase in this plan wires it in.
- **pgmq/orchestrator worker DAG.** Deferred until a real timeout or concurrency
  problem shows up; current request volume (a hackathon/pilot-scale app) doesn't
  need it. Revisit if interpretation requests start exceeding ~10s.
- **`packages/contracts` JSON-Schema-to-codegen pipeline.** Useful once more than
  one person is editing both the TS and Python sides of a contract concurrently.
  Right now the schemas (`schemas/therapy.py`, `schemas/variant.py`) are hand-kept
  in sync by one codebase; add codegen when that stops being true.
- **`care_team` many-to-many junction table** replacing `patients.primary_doctor_id`.
  Real limitation (one doctor per patient, permanently) but not blocking for a
  pilot. Flag as a follow-up migration once multi-doctor care is an actual
  requirement, not a hypothetical.
- **Crypto-shredding / per-patient key wrapping**, **mTLS between services**,
  **containerizing the ML tier**, **hash-chain nightly pg_cron verification.**
  All real hardening ideas, all appropriate once this handles real patient data
  in front of real users — premature while it's synthetic-data + pilot-scale.
- **Trajectory matching (Product 1 in the earlier sketch).** Not started here at
  all — it's a distinct product surface (event-sequence pattern matching) with
  its own schema and its own leakage risks, and depends on real longitudinal
  patient event data this project doesn't yet collect. Worth a separate plan if
  and when it's actually wanted, not bundled into this one.

---

## 4. Open decisions for you

1. **Patient-facing visibility of raw classifications/drug rankings** (Phase B2)
   — my default hides them from patients entirely (dashboard shows plain-language
   status only). Confirm, or specify a different policy.
2. **Review/sign-off requirement before therapy ranking** (Phase B5) — requires a
   small schema addition (reviewed_by/reviewed_at). Confirm you want this
   before B5 touches the schema.
3. **Whether to formally deprecate the legacy `/api/*` demo path** once B3 lands,
   or keep it running indefinitely as a showcase — currently the plan keeps it
   frozen per the existing "preserved unchanged" invariant, but that's worth a
   deliberate decision now that a real path exists alongside it.
4. **Scope of the ClinVar/gnomAD data-access problem** (see `docs/PLAN_ML_MODELS.md`
   §4.1) — does it block ACMG v2's own PS1/PM5/PM2/BA1/BS1 evidence lookups, or
   was it specifically the bulk training-scale pull the dropped classifier
   needed? This affects how much of ACMG v2 can actually run in production and
   should be confirmed before Phase B3 is treated as low-risk.
