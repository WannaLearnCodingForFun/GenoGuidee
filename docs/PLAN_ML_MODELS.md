# GenoGuide — ML Models Plan (2 engineers, 2 models)

**Status:** PLANNING ONLY. Nothing in this document has been executed — no training
run, no code change. Each section below is a self-contained brief for one ML
engineer, sized so two people can work in parallel on separate machines with
minimal cross-dependency.

**Revision note:** the earlier version of this plan included a third component — a
supervised pathogenicity classifier (logreg/xgboost on a large ClinVar+gnomAD
corpus). **That model is dropped from this plan at your instruction**: the
training-scale data it depended on (the full ClinVar dump + gnomAD v4 constraint
data, at the volume needed to reproduce/extend the real trained artifacts found in
`models/production/*.joblib`) is not publicly accessible to this team going
forward. Production now targets exactly two ML models, both already real and
already producing legitimate results:

1. **Drug / therapy ranker** — already trained, real CIViC + DGIdb data.
2. **Cohort / nearest-mutation similarity matcher** — new build, reusing existing
   HPO similarity code; now takes on more importance than originally scoped,
   since it's the closest thing this system has to an evidence-based
   "how does this mutation compare to known ones" signal in the absence of a
   standalone classifier (see §0.2).

---

## 0. What changes with the classifier dropped

### 0.1 What still classifies variants
Dropping the supervised classifier does **not** mean nothing classifies variants.
`interpretation/acmg_v2.py` — the deterministic ACMG/AMP 2015 28-criterion rule
engine — is separate code, already real, and was never the thing you're dropping.
It still produces the authoritative classification (pathogenic / likely
pathogenic / VUS / likely benign / benign) from rule-based evidence, not from a
trained model. **Confirm this explicitly before treating it as settled** (open
decision §4.1): the rule engine's own evidence sources (ClinVar lookups for
PS1/PM5, gnomAD frequency for PM2/BA1/BS1) may draw on some of the same data as
the dropped classifier. If *that* access is also gone, the rule engine itself
degrades (falls back to `NOT_EVALUABLE` more often — which is its documented,
safe failure mode, not a crash), and this needs to be known now, not discovered
mid-build.

### 0.2 What the similarity matcher now needs to carry
With no supervised classifier, the similarity matcher (§2 below) is doing more
work than "nice-to-have cohort context." It becomes the system's main
*instance-based* evidence source: "here are the closest known, already-classified
mutations to this patient's variant, and here's how close they actually are."
That's a legitimate, real technique (nearest-neighbor / case-based reasoning) —
it is not a replacement for a trained classifier's calibrated probability, and
this plan does not pretend it is. Say so plainly in any UI that surfaces it:
"nearest known cases," not "predicted pathogenicity."

---

## 1. Model 1 — Drug / therapy ranker

*(Unchanged from the prior version of this plan — reproduced here so this
document is complete on its own.)*

### Current state
- Real trained Gradient Boosting model: `Medical_DrugRecommendation/model/model.pkl`,
  15-D feature extractor (`model/features.py`), trained on real CIViC + DGIdb data
  (`Medical_DrugRecommendation/Data/*.tsv`).
- Pipeline: `candidate_generator.py` → `evidence_ranker.py` (deterministic A–E
  evidence-level baseline) → `drug_ranker.py` (hybrid: ML + deterministic safety
  rules) → `recommender.py` (orchestrator).
- Reachable two ways: local in-process (default — `services/drug_recommendation.py`
  imports `recommender.py` directly, no network hop) and an optional remote
  override over ngrok for a separately-hosted copy of the same engine. The local
  path is what matters for reliability.
- **No abstention path** — confirmed by reading `drug_ranker.py`/`recommender.py`:
  it always returns *some* ranked list once a gene/variant/disease reaches it.
  This is the highest-risk gap on the ML side — a clinician reading rank 1 for an
  out-of-coverage input has no signal the model is guessing.

### Required modifications
1. **Re-verify the existing benchmark.** `model/evaluate.py` exists — run/extend
   it and produce a dated, versioned report with real numbers before claiming
   anything about model quality. Don't reuse old numbers without re-confirming
   them against the current `model.pkl`.
2. **Add abstention.** Out-of-coverage gene, unmapped indication, or a variant
   class that isn't a clean substitution → `{"recommendations": [], "abstained":
   true, "abstain_reason": "..."}`. Never a ranked list for out-of-coverage input.
3. **Coverage map.** Enumerate every (gene, variant class, indication) triple the
   CIViC/DGIdb training data actually supports; emit a versioned
   `p3_coverage.json`. The normalization bridge (Backend Plan, Phase B4) and the
   frontend's "not applicable" messaging both depend on this — produce it before
   those land. If the data can't support a precise list, say so, don't
   approximate silently.
4. **Negative controls.** Gene–drug pairs with **no** published association must
   not rank top-3 for any indication. If any do, the model is likely
   pattern-matching on gene popularity — report this rather than tuning the eval
   to pass.
5. **Adversarial contract tests.** The connector's docstring already claims no
   patient identifiers are sent off-box — prove it under test. Send
   patient_id/name/mrn-shaped fields mixed into the payload and assert they're
   rejected/stripped before reaching the local engine or any remote host, and
   assert nothing sensitive appears in logs.

### Data needed
Already present in `Medical_DrugRecommendation/Data/*.tsv`. If a fresher
CIViC/DGIdb pull is needed for a credible coverage/negative-control analysis, say
so explicitly and ask before treating stale nightly snapshots as current.

### Integration point
Takes `{gene, protein_short, disease}` from the normalization bridge (Backend
Plan Phase B4). The therapy gate (Backend Plan Phase B5) decides whether this
model is even called — do not bypass the gate from inside this model's code.

### Paste-ready prompt
```
Read Medical_DrugRecommendation/README.md, recommendation/recommender.py,
drug_ranker.py, evidence_ranker.py, model/evaluate.py, and
backend/app/services/drug_recommendation.py.

1. Run/extend model/evaluate.py and produce a dated, versioned benchmark report
   with real, freshly-computed numbers (precision@1, precision@3 against CIViC/
   DGIdb evidence levels A/B). Do not report old numbers without re-verifying.

2. Add an abstention path: out-of-coverage gene, unmapped indication, or
   non-substitution variant class -> {"recommendations": [], "abstained": true,
   "abstain_reason": "..."}. Never a ranked list for these cases.

3. Build evals/p3_coverage.json enumerating every (gene, variant class,
   indication) triple the training data actually supports. If the data can't
   support this precisely, stop and say so rather than approximating.

4. Negative-control test: gene-drug pairs with no published association must
   not rank top-3 for any indication. Report the result honestly even if it
   fails.

5. Adversarial contract test: PHI-shaped fields (patient_id, name, mrn) in the
   input must never reach the local engine's feature extraction or any log line.

Acceptance: dated benchmark report exists; abstention path has unit tests;
p3_coverage.json exists and is referenced by name in the report; negative
control and PHI tests exist and their real pass/fail result is stated plainly.
```

---

## 2. Model 2 — Cohort / nearest-mutation similarity matcher

### Purpose (reframed)
Given a patient's variant (gene, consequence, protein change) and phenotype (HPO
terms), find the **nearest known, already-catalogued mutations** to it — from
reference data (e.g. ClinVar) and/or whatever real prior-case data this project
actually holds — and surface their classification, supporting evidence, and how
close the match actually is. This is now the system's primary
"how does this compare to what's already known" signal, since there is no
standalone supervised classifier. It answers a case-based question ("what's this
most like"), not a calibrated-probability question ("what is this").

### Current state
Not wired end-to-end, but not starting from zero: real, working phenotype
similarity code already exists — `backend/app/phenotype/similarity.py` (Resnik,
Lin, Jaccard information-content similarity over HPO terms) and
`backend/app/phenotype/ontology.py`. `/api/v1/phenotype/match`, `/gene-ranking`,
`/disease-ranking` already expose parts of this. What's missing is combining it
with variant-level similarity (same gene/consequence/protein-region proximity)
into one nearest-neighbor query, and returning matched reference cases with their
classification and evidence — not just a phenotype score in isolation.

### Required build
1. **Reference corpus.** Decide what "known mutations" means here now that the
   large-scale ClinVar training corpus is off the table. Two tiers, in order of
   preference — confirm which is actually available before building either:
   - **Reference lookups (not bulk training):** querying ClinVar's own
     variant-summary API/data for a *specific* gene/variant on demand is a much
     smaller ask than the 3.9M-row bulk pull the dropped classifier needed, and
     may still be within reach even if bulk access isn't. Confirm this
     explicitly — don't assume it inherits the same access problem.
   - **Whatever real prior-case data this project actually holds** (e.g. cases
     already run through this system, if any exist) — smaller, but has the
     advantage of being definitely accessible and definitely relevant to this
     deployment specifically.
   Do not silently substitute a synthetic dataset for either tier and present
   results as if they were real reference matches — if neither tier is
   available at meaningful scale, say so and scope this model down explicitly
   (e.g. "matches within the existing 120-variant curated demo set only, labeled
   as such") rather than quietly overstating what it's matching against.
2. **Similarity function.** Combine:
   - Variant proximity: same gene weighted heavily; same/adjacent
     consequence type; protein-position proximity where applicable.
   - Phenotype proximity: existing Resnik/Lin/Jaccard HPO similarity — reuse,
     don't reimplement.
   A simple weighted combination is fine to start; this does not need to be a
   learned metric. Index with a k-d tree or even brute-force distance — check
   the actual row count of whatever reference corpus is settled on in step 1
   before reaching for anything more elaborate than that.
3. **Query API.** Given a query variant + phenotype set, return the k nearest
   reference cases, each with: its own classification (from whatever labeled the
   reference corpus — e.g. ClinVar's own assertion, clearly attributed as such,
   not presented as this system's opinion), its evidence source, and a
   similarity breakdown (which specific features — which HPO terms, which
   variant properties — drove the match). Explainability is required, not
   optional: a doctor needs to see *why* something matched, per the "every
   output shows its basis" norm.
4. **No outcome fabrication.** If real per-case *outcome* data doesn't exist
   anywhere in this project's data (check `research/data/processed/`,
   `backend/app/dataset.py` before assuming either way), do not add an outcomes
   field. Scope this model to classification-and-evidence similarity only in
   that case, and say so.
5. **Backtest — this is the real validity check.** Leave-one-out (or k-fold): for
   a held-out reference case, do its k nearest neighbors' classifications
   actually agree with its own classification at a rate meaningfully above
   chance? Report the real number. A similarity matcher whose "nearest" cases
   don't actually agree in classification more often than random pairing is not
   doing useful clinical work, however plausible the distance metric looks on
   paper — this is the single most important thing to get an honest number on
   before this ships to a clinician's screen.

### Data needed
Depends entirely on which reference-corpus tier (step 1) turns out to be
available. Confirm before starting the build, not after — this changes the
scope materially (a per-variant ClinVar lookup vs. a small internal case set are
different-sized engineering problems).

### Integration point
New, additive, read-only endpoint — e.g. `/api/v1/similar-cases`. Does not modify
any existing endpoint's contract. Surfaces in the doctor UI (Backend Plan Phase
B3/B6) alongside whatever ACMG v2 produces, clearly labeled as case-based
evidence, not a replacement classification.

### Paste-ready prompt
```
Read backend/app/phenotype/similarity.py, phenotype/ontology.py, the existing
/api/v1/phenotype/* routes in api/v1.py, and interpretation/acmg_v2.py (for
how PS1/PM5 already do a narrower version of "is this like a known pathogenic
variant" lookup — don't duplicate that logic, understand it first).

Before writing any model code: confirm what reference-mutation data is actually
and currently accessible — a live/on-demand ClinVar lookup for a specific
gene+variant (much smaller ask than a bulk training pull), some internal
prior-case data if any exists, or neither at meaningful scale. Report this
before proceeding; do not assume access transfers from what was previously used
for the (now-dropped) classifier.

Build a cohort similarity matcher: given a query variant (gene, consequence,
protein position) + HPO phenotype set, return the k nearest reference cases,
each carrying its own classification (attributed to its real source, e.g.
"ClinVar: Pathogenic, reviewed by expert panel" — never presented as this
system's own verdict), plus a similarity breakdown showing which variant
features and which HPO terms drove the match. Reuse the existing Resnik/Lin/
Jaccard similarity code for the phenotype half; do not reimplement it.

Do not add an outcomes field unless real per-case outcome data is confirmed to
exist in this project's data. If it doesn't, say so and scope to
classification-and-evidence similarity only.

Backtest: leave-one-out validity check on whatever reference corpus is used —
do a held-out case's k nearest neighbors agree with its own classification at
a rate above chance? Report the real number, including if it's weak.

Add a new additive endpoint (e.g. /api/v1/similar-cases) — do not modify
existing phenotype or interpret endpoints' contracts.

Acceptance: the reference-data access question is answered and documented
before the model is built on top of it; the backtest number is reported
honestly; the endpoint is additive and tested; every returned case shows why
it matched and where its own classification came from.
```

---

## 3. What's not being built (and why)

- **Supervised pathogenicity classifier** — dropped at your instruction; the
  training-scale ClinVar + gnomAD data it needs is not publicly accessible to
  this team. The existing `models/production/*.joblib` artifacts remain in the
  repo as historical/reference artifacts only — do not wire them into any new
  work under this plan, and do not present their previously-recorded benchmark
  numbers as describing a model currently in production.
- **ESM-2 fine-tuned embeddings / multimodal fusion / stacked ensemble** — no
  protein sequence source configured; was already interface-only before the
  classifier was dropped, and dropping the classifier removes the main reason
  to build toward it. Not revisited unless a new sequence data source is
  actually acquired.
- **Trajectory sequence model (event-history pattern learning)** — a distinct
  product surface needing real longitudinal event data this project doesn't
  collect yet. Out of scope here regardless of the classifier decision.
- **An LLM layer** — deliberately omitted per existing project convention; no
  reason surfaced to reconsider that.

## 4. Open decisions for you

1. **Does the ACMG v2 rule engine's own data access still work?** (§0.1) It
   depends on ClinVar (PS1/PM5 lookups) and gnomAD (PM2/BA1/BS1 frequency
   evidence) — confirm whether the data-access problem that killed the
   classifier also blocks these, or whether it was specifically the bulk
   training-scale pull that's gone. This materially changes what the rule
   engine can still evaluate.
2. **Reference-corpus tier for the similarity matcher** (§2, step 1) — on-demand
   per-variant ClinVar lookup, internal prior-case data, or a scoped-down demo
   set. Needs an answer before Model 2's engineer can size the work.
3. **Outcome data for the similarity matcher** — confirm whether real outcome
   tracking exists anywhere in this project's data; if not, confirm
   "classification-and-evidence similarity only" is acceptable v1 scope.
4. **Therapy coverage scope** (Model 1) — formally scope v1 to substitution
   variants only vs. investing in retraining for other variant classes. Product
   decision, not an engineering default.
