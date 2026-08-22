"use client";

import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  ClipboardList,
  Dna,
  FileUp,
  FlaskConical,
  GitMerge,
  Info,
  Loader2,
  Pill,
  Scale,
  ShieldCheck,
  Stethoscope,
  X,
  XCircle,
} from "lucide-react";
import {
  api,
  type PatientHistory,
  type VariantListItem,
  type WorkupResult,
} from "@/lib/api";
import { listAllAccessibleVariants, type AccessibleVariant } from "@/lib/uploads";
import { variantLabel } from "@/lib/vcf";
import { classColor, formatAf } from "@/lib/ui";

type Source = "curated" | "upload";

const EMPTY_HISTORY: PatientHistory = {
  age: null,
  sex: null,
  diagnosis: null,
  presenting_complaint: null,
  phenotypes: [],
  prior_conditions: [],
  medications: [],
  family_history_positive: false,
  family_details: null,
  consent_confirmed: false,
};

const STAGE_ICONS = {
  intake: ClipboardList,
  triple: Dna,
  classification: BrainCircuit,
  reconciliation: GitMerge,
  medication: Pill,
} as const;

function stageTone(status: string): string {
  if (["COMPLETE", "CONCORDANT", "AVAILABLE"].includes(status))
    return "border-success/40 bg-success/10 text-success";
  if (["DISCORDANT", "PARTIAL", "NOT_INDICATED"].includes(status))
    return "border-warning/40 bg-warning/10 text-warning";
  if (status === "INSUFFICIENT_INPUT" || status.startsWith("ENGINE_"))
    return "border-error/40 bg-error/10 text-error";
  return "border-navy-950/15 bg-navy-950/5 text-muted";
}

/* ---------------------------------------------------------------- chips -- */

function ChipInput({
  label,
  placeholder,
  values,
  onChange,
  hint,
}: {
  label: string;
  placeholder: string;
  values: string[];
  onChange: (next: string[]) => void;
  hint?: string;
}) {
  const [draft, setDraft] = useState("");

  function commit() {
    const v = draft.trim();
    if (!v || values.includes(v)) {
      setDraft("");
      return;
    }
    onChange([...values, v]);
    setDraft("");
  }

  function onKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit();
    } else if (e.key === "Backspace" && !draft && values.length) {
      onChange(values.slice(0, -1));
    }
  }

  return (
    <div>
      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-muted">
        {label}
      </label>
      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-navy-950/10 bg-panel2 px-2.5 py-2 transition-colors focus-within:border-cyan/50">
        {values.map((v) => (
          <span
            key={v}
            className="inline-flex items-center gap-1 rounded-md border border-cyan/30 bg-cyan/10 px-2 py-0.5 text-xs text-cyan"
          >
            {v}
            <button
              type="button"
              onClick={() => onChange(values.filter((x) => x !== v))}
              className="opacity-60 transition-opacity hover:opacity-100"
            >
              <X className="size-3" />
            </button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
          onBlur={commit}
          placeholder={values.length ? "" : placeholder}
          className="min-w-[8rem] flex-1 bg-transparent py-0.5 text-sm outline-none"
        />
      </div>
      {hint && <p className="mt-1 text-[11px] text-muted">{hint}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ page -- */

export default function ClinicalWorkup() {
  const [source, setSource] = useState<Source>("curated");
  const [curated, setCurated] = useState<VariantListItem[]>([]);
  const [curatedId, setCuratedId] = useState("VAR-BRCA1-5266DUP");
  const [uploaded, setUploaded] = useState<AccessibleVariant[]>([]);
  const [uploadedId, setUploadedId] = useState<number | null>(null);
  const [loadingUploads, setLoadingUploads] = useState(false);

  const [history, setHistory] = useState<PatientHistory>(EMPTY_HISTORY);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<WorkupResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.variants().then(setCurated).catch(() => setError("Backend not reachable on port 8000."));
  }, []);

  useEffect(() => {
    if (source !== "upload" || uploaded.length) return;
    setLoadingUploads(true);
    listAllAccessibleVariants()
      .then((rows) => {
        setUploaded(rows);
        setUploadedId((cur) => cur ?? rows[0]?.id ?? null);
      })
      .catch(() => setUploaded([]))
      .finally(() => setLoadingUploads(false));
  }, [source, uploaded.length]);

  const selectedUploaded = uploaded.find((v) => v.id === uploadedId) ?? null;
  const canRun =
    history.consent_confirmed &&
    (source === "curated" ? !!curatedId : !!selectedUploaded);

  function set<K extends keyof PatientHistory>(key: K, value: PatientHistory[K]) {
    setHistory((h) => ({ ...h, [key]: value }));
  }

  async function run() {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.workup({
        variant_id: source === "curated" ? curatedId : null,
        uploaded_variant:
          source === "upload" && selectedUploaded
            ? {
                chrom: selectedUploaded.chrom,
                pos: selectedUploaded.pos,
                ref: selectedUploaded.ref,
                alt: selectedUploaded.alt,
                gene: selectedUploaded.gene,
                transcript: selectedUploaded.transcript,
                hgvs_c: selectedUploaded.hgvs_c,
                hgvs_p: selectedUploaded.hgvs_p,
                consequence: selectedUploaded.consequence,
                gnomad_af: selectedUploaded.gnomad_af,
                cadd: selectedUploaded.cadd,
                revel: selectedUploaded.revel,
                spliceai: selectedUploaded.spliceai,
                phylop: selectedUploaded.phylop,
              }
            : null,
        history,
        subject_ref: selectedUploaded?.upload?.patient_id ?? null,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Workup failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="absolute inset-0 grid-texture" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_30%_0%,rgba(180,24,45,0.06),transparent_70%)]" />

      <div className="relative z-10 mx-auto max-w-6xl px-8 py-12">
        <header className="mb-8">
          <h1 className="flex items-center gap-3 text-2xl font-bold tracking-tight">
            <Stethoscope className="size-6 text-cyan" />
            Clinical Workup
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-muted">
            Record the patient&apos;s history alongside a variant, and the workup runs the full
            chain: gene &middot; variant &middot; disease, then classification, then AI/ACMG
            reconciliation, then a medication shortlist gated on the verdict.
          </p>
        </header>

        {/* Stage rail */}
        <StageRail result={result} running={running} />

        {/* --------------------------------------------------- intake form -- */}
        <section className="card card-glow-cyan mt-6 p-6">
          <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
            <ClipboardList className="size-3.5" /> Step 1 &middot; Intake
          </h2>

          {/* variant source */}
          <div className="mb-5">
            <label className="mb-2 block text-xs font-semibold uppercase tracking-widest text-muted">
              Variant under review
            </label>
            <div className="mb-3 inline-flex rounded-xl border border-navy-950/10 bg-panel2/60 p-1">
              {([
                { id: "curated" as Source, label: "Demo case", icon: FlaskConical },
                { id: "upload" as Source, label: "Uploaded VCF", icon: FileUp },
              ]).map((o) => (
                <button
                  key={o.id}
                  type="button"
                  onClick={() => setSource(o.id)}
                  className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                    source === o.id
                      ? "border border-cyan/40 bg-cyan/10 text-cyan"
                      : "border border-transparent text-muted hover:text-fg"
                  }`}
                >
                  <o.icon className="size-4" />
                  {o.label}
                  {o.id === "upload" && uploaded.length > 0 && (
                    <span className="rounded-full bg-cyan/15 px-1.5 text-[10px] tabular-nums">
                      {uploaded.length}
                    </span>
                  )}
                </button>
              ))}
            </div>

            {source === "curated" ? (
              <select
                value={curatedId}
                onChange={(e) => setCuratedId(e.target.value)}
                className="w-full max-w-xl rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none focus:border-cyan/50"
              >
                {curated.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.gene} {v.hgvs_c} ({v.consequence})
                    {v.showcase_label ? ` — ${v.showcase_label}` : ""}
                  </option>
                ))}
              </select>
            ) : loadingUploads ? (
              <p className="flex items-center gap-2 text-sm text-muted">
                <Loader2 className="size-4 animate-spin" /> Loading uploaded variants&hellip;
              </p>
            ) : uploaded.length === 0 ? (
              <p className="text-sm text-muted">
                No uploaded variants yet.{" "}
                <Link href="/upload" className="text-cyan hover:underline">
                  Upload a VCF
                </Link>{" "}
                to use one here.
              </p>
            ) : (
              <select
                value={uploadedId ?? ""}
                onChange={(e) => setUploadedId(Number(e.target.value))}
                className="w-full max-w-xl rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none focus:border-cyan/50"
              >
                {uploaded.map((v) => (
                  <option key={v.id} value={v.id}>
                    {variantLabel(v)} ({v.consequence ?? "unannotated"}) —{" "}
                    {v.upload?.filename ?? "file"}
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="h-px bg-navy-950/8" />

          {/* history */}
          <p className="mb-4 mt-5 text-xs font-semibold uppercase tracking-widest text-muted">
            Past medical history
          </p>

          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-muted">
                Age
              </label>
              <input
                type="number"
                min={0}
                max={120}
                value={history.age ?? ""}
                onChange={(e) => set("age", e.target.value ? Number(e.target.value) : null)}
                className="w-full rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none focus:border-cyan/50"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-muted">
                Sex
              </label>
              <select
                value={history.sex ?? ""}
                onChange={(e) => set("sex", e.target.value || null)}
                className="w-full rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none focus:border-cyan/50"
              >
                <option value="">Not stated</option>
                <option value="female">Female</option>
                <option value="male">Male</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-muted">
                Diagnosis / indication
              </label>
              <input
                value={history.diagnosis ?? ""}
                onChange={(e) => set("diagnosis", e.target.value || null)}
                placeholder="e.g. breast cancer, NSCLC"
                className="w-full rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none focus:border-cyan/50"
              />
            </div>
          </div>

          <div className="mt-4">
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-muted">
              Presenting complaint
            </label>
            <textarea
              rows={2}
              value={history.presenting_complaint ?? ""}
              onChange={(e) => set("presenting_complaint", e.target.value || null)}
              placeholder="What brought the patient in?"
              className="w-full resize-y rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none focus:border-cyan/50"
            />
          </div>

          <div className="mt-4 grid gap-4 md:grid-cols-3">
            <ChipInput
              label="Phenotypes / signs"
              placeholder="Type and press Enter"
              values={history.phenotypes}
              onChange={(v) => set("phenotypes", v)}
              hint="Free text — matched against the gene's known presentation."
            />
            <ChipInput
              label="Prior conditions"
              placeholder="Type and press Enter"
              values={history.prior_conditions}
              onChange={(v) => set("prior_conditions", v)}
            />
            <ChipInput
              label="Current medications"
              placeholder="Type and press Enter"
              values={history.medications}
              onChange={(v) => set("medications", v)}
            />
          </div>

          <div className="mt-4 rounded-xl border border-navy-950/10 bg-panel2/50 p-4">
            <label className="flex cursor-pointer items-center gap-2.5 text-sm">
              <input
                type="checkbox"
                checked={history.family_history_positive}
                onChange={(e) => set("family_history_positive", e.target.checked)}
                className="size-4 accent-[#b4182d]"
              />
              Positive family history
            </label>
            {history.family_history_positive && (
              <textarea
                rows={2}
                value={history.family_details ?? ""}
                onChange={(e) => set("family_details", e.target.value || null)}
                placeholder="Affected relatives, ages at diagnosis…"
                className="mt-3 w-full resize-y rounded-lg border border-navy-950/10 bg-panel px-3.5 py-2.5 text-sm outline-none focus:border-cyan/50"
              />
            )}
          </div>

          <label className="mt-4 flex cursor-pointer items-start gap-2.5 text-sm text-muted">
            <input
              type="checkbox"
              checked={history.consent_confirmed}
              onChange={(e) => set("consent_confirmed", e.target.checked)}
              className="mt-0.5 size-4 accent-[#b4182d]"
            />
            <span>
              I confirm consent is on record for this analysis.{" "}
              <span className="text-muted/70">
                History stays on your server; only hashes reach the provenance ledger.
              </span>
            </span>
          </label>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              onClick={run}
              disabled={!canRun || running}
              className="group inline-flex items-center gap-2 rounded-xl border border-cyan/50 bg-cyan/15 px-6 py-3 text-sm font-bold tracking-wide text-cyan transition-all hover:bg-cyan/25 hover:shadow-[0_0_28px_-6px_#b4182d] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {running ? <Loader2 className="size-4 animate-spin" /> : <Activity className="size-4" />}
              RUN CLINICAL WORKUP
              {!running && <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />}
            </button>
            {!history.consent_confirmed && (
              <span className="text-xs text-muted">Confirm consent to enable the run.</span>
            )}
          </div>

          {error && (
            <p className="mt-4 flex items-center gap-2 text-sm text-error">
              <XCircle className="size-4" /> {error}
            </p>
          )}
        </section>

        {/* ------------------------------------------------------- results -- */}
        <AnimatePresence>
          {result && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45 }}
              className="mt-6 space-y-6"
            >
              <TripleStage result={result} />
              <ClassificationStage result={result} />
              <ReconciliationStage result={result} />
              <MedicationStage result={result} />
              <ConsiderationsCard result={result} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------- stage rail -- */

function StageRail({ result, running }: { result: WorkupResult | null; running: boolean }) {
  const stages =
    result?.stages ??
    ([
      { id: "intake", label: "Intake", status: "PENDING" },
      { id: "triple", label: "Gene · Variant · Disease", status: "PENDING" },
      { id: "classification", label: "Classification", status: "PENDING" },
      { id: "reconciliation", label: "AI vs ACMG", status: "PENDING" },
      { id: "medication", label: "Medication", status: "PENDING" },
    ] as WorkupResult["stages"]);

  return (
    <div className="card flex flex-wrap items-stretch gap-y-3 p-4">
      {stages.map((s, i) => {
        const Icon = STAGE_ICONS[s.id];
        const pending = s.status === "PENDING";
        return (
          <div key={s.id} className="flex items-center">
            <div
              className={`flex w-[150px] flex-col items-center gap-1.5 rounded-lg border px-2 py-3 text-center transition-all ${
                pending ? "border-navy-950/8 opacity-45" : stageTone(s.status)
              }`}
            >
              {running && pending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Icon className="size-4" />
              )}
              <span className="text-[11px] font-semibold leading-tight">{s.label}</span>
              <span className="mono text-[9px] uppercase tracking-wider opacity-80">
                {s.status.replace(/_/g, " ")}
              </span>
            </div>
            {i < stages.length - 1 && <ArrowRight className="mx-1 size-3.5 shrink-0 text-cyan/40" />}
          </div>
        );
      })}
    </div>
  );
}

/* -------------------------------------------------------- stage 2: triple -- */

function TripleStage({ result }: { result: WorkupResult }) {
  const t = result.triple;
  const cards = [
    { label: "Gene", value: t.gene ?? "—", sub: t.gene_disease ?? "no curated association", icon: Dna },
    { label: "Variant", value: t.variant_display, sub: `token: ${t.variant}`, icon: FlaskConical },
    { label: "Disease", value: t.disease ?? "—", sub: t.disease_source ?? "not resolved", icon: Stethoscope },
  ];

  return (
    <section className="card p-6">
      <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
        <Dna className="size-3.5" /> Step 2 &middot; Gene · Variant · Disease
      </h2>

      <div className="grid gap-3 md:grid-cols-3">
        {cards.map((c) => (
          <div key={c.label} className="rounded-xl border border-navy-950/10 bg-panel2/60 p-4">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-muted">
              <c.icon className="size-3.5 text-cyan" />
              {c.label}
            </div>
            <p className="mono mt-2 break-words text-lg font-bold">{c.value}</p>
            <p className="mt-1 text-[11px] text-muted">{c.sub}</p>
          </div>
        ))}
      </div>

      <p className="mt-4 flex items-start gap-2 text-xs text-muted">
        <Info className="mt-0.5 size-3.5 shrink-0 text-cyan" />
        {t.token_note}
      </p>

      <PhenotypeOverlapRow result={result} />
    </section>
  );
}

function PhenotypeOverlapRow({ result }: { result: WorkupResult }) {
  const o = result.phenotype_overlap;
  const tone =
    o.status === "SUPPORTED"
      ? "border-success/35 bg-success/5 text-success"
      : o.status === "NO_OVERLAP"
        ? "border-warning/40 bg-warning/5 text-warning"
        : "border-navy-950/10 bg-navy-950/[0.03] text-muted";

  return (
    <div className={`mt-3 rounded-lg border p-3.5 ${tone}`}>
      <p className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest">
        {o.status === "SUPPORTED" ? (
          <CheckCircle2 className="size-3.5" />
        ) : (
          <AlertTriangle className="size-3.5" />
        )}
        History &harr; gene overlap: {o.status.replace(/_/g, " ")}
      </p>
      <p className="mt-1.5 text-xs text-muted">{o.note}</p>
    </div>
  );
}

/* ------------------------------------------------ stage 3: classification -- */

function ClassificationStage({ result }: { result: WorkupResult }) {
  const cc = classColor(result.acmg.classification);
  const probs = Object.entries(result.ml.probabilities).sort((a, b) => b[1] - a[1]);

  return (
    <section className="card p-6">
      <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
        <BrainCircuit className="size-3.5" /> Step 3 &middot; Classification
      </h2>

      <div className="grid gap-5 lg:grid-cols-2">
        {/* AI path */}
        <div className="rounded-xl border border-violet/25 bg-violet/[0.04] p-4">
          <h3 className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.2em] text-violet">
            <BrainCircuit className="size-3.5" /> AI path — ESM-2 + XGBoost
          </h3>
          <p className="mt-3 text-xl font-bold">{result.ml.top_class}</p>
          <p className="text-xs text-muted">
            confidence {(result.ml.confidence * 100).toFixed(1)}% · {result.ml.engine}
          </p>
          <div className="mt-3 space-y-1.5">
            {probs.map(([k, v]) => (
              <div key={k} className="flex items-center gap-2">
                <span className="w-32 shrink-0 text-[11px] capitalize text-muted">
                  {k.replace(/_/g, " ")}
                </span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-navy-950/10">
                  <div className="h-full rounded-full bg-violet" style={{ width: `${v * 100}%` }} />
                </div>
                <span className="mono w-12 shrink-0 text-right text-[10px] text-muted">
                  {(v * 100).toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11px] text-muted">
            ESM-2 delta {result.esm2.delta_score} · {result.esm2.mode}
          </p>
        </div>

        {/* ACMG path */}
        <div className="rounded-xl border border-cyan/25 bg-cyan/[0.04] p-4">
          <h3 className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.2em] text-cyan">
            <Scale className="size-3.5" /> ACMG path — deterministic rules
          </h3>
          <p className={`mt-3 text-xl font-bold ${cc.text}`}>{result.acmg.classification}</p>
          <p className="text-xs text-muted">{result.acmg.framework}</p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {result.acmg.met_criteria.length ? (
              result.acmg.met_criteria.map((c) => (
                <span
                  key={c}
                  className="mono rounded border border-cyan/40 bg-cyan/10 px-2 py-0.5 text-[10px] font-bold text-cyan"
                >
                  {c}
                </span>
              ))
            ) : (
              <span className="text-xs text-muted">No criteria met.</span>
            )}
          </div>
          <p className="mt-3 text-[11px] text-muted">{result.acmg.rule_note}</p>
        </div>
      </div>

      {/* variant facts */}
      <div className="mt-4 flex flex-wrap gap-x-8 gap-y-2 rounded-lg border border-navy-950/8 bg-panel2/40 px-4 py-3 text-xs">
        {[
          ["Consequence", result.variant.consequence],
          ["gnomAD AF", formatAf(result.variant.gnomad_af)],
          ["CADD", result.variant.cadd ?? "—"],
          ["REVEL", result.variant.revel ?? "—"],
          ["SpliceAI", result.variant.spliceai ?? "—"],
          ["phyloP", result.variant.phylop ?? "—"],
        ].map(([k, v]) => (
          <span key={String(k)}>
            <span className="text-muted">{k}: </span>
            <span className="mono font-semibold">{String(v)}</span>
          </span>
        ))}
      </div>

      {result.variant_source === "upload" && result.missing_evidence.length > 0 && (
        <div className="mt-4 rounded-lg border border-warning/35 bg-warning/5 p-4">
          <p className="text-[10px] font-bold uppercase tracking-widest text-warning">
            Uploaded variant — evidence a VCF cannot carry
            {result.annotation_completeness
              ? ` · annotations ${result.annotation_completeness.percent}% complete`
              : ""}
          </p>
          <ul className="mt-2 space-y-1">
            {result.missing_evidence.map((m) => (
              <li key={m.criterion} className="flex gap-2 text-xs text-muted">
                <span className="mono shrink-0 font-bold text-warning">{m.criterion}</span>
                <span>{m.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

/* ----------------------------------------------- stage 4: reconciliation -- */

function ReconciliationStage({ result }: { result: WorkupResult }) {
  const r = result.reconciliation;
  const concordant = r.status === "CONCORDANT";
  const cc = classColor(r.final_classification);

  return (
    <section
      className={`card p-6 ${concordant ? "card-glow-success" : "card-glow-warning"}`}
    >
      <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
        <GitMerge className="size-3.5" /> Step 4 &middot; AI vs ACMG reconciliation
      </h2>

      <div className="flex flex-wrap items-center gap-x-10 gap-y-4">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-muted">Status</p>
          <p
            className={`mt-1 flex items-center gap-2 text-2xl font-black ${
              concordant ? "text-success" : "text-warning"
            }`}
          >
            {concordant ? <CheckCircle2 className="size-5" /> : <AlertTriangle className="size-5" />}
            {r.status}
          </p>
          <p className={`text-xs font-semibold ${concordant ? "text-success" : "text-warning"}`}>
            {r.confidence}
          </p>
        </div>

        <div>
          <p className="text-[10px] uppercase tracking-widest text-muted">Final classification</p>
          <p className={`mt-1 text-2xl font-black ${cc.text}`}>{r.final_classification}</p>
          <p className="text-xs text-muted">decided by the ACMG rule engine</p>
        </div>

        <div className="min-w-[220px] flex-1">
          <p className="text-[10px] uppercase tracking-widest text-muted">Buckets compared</p>
          <p className="mono mt-1 text-xs">
            AI <span className="text-violet">{r.ml_bucket}</span> vs ACMG{" "}
            <span className="text-cyan">{r.acmg_bucket}</span>
          </p>
        </div>
      </div>

      <p className="mt-4 rounded-lg border border-navy-950/8 bg-panel2/50 px-4 py-3 text-sm text-muted">
        {r.note}
      </p>
      <p className="mt-2 flex items-center gap-2 text-[11px] text-muted">
        <ShieldCheck className="size-3.5 text-violet" />
        {r.authority}
      </p>
    </section>
  );
}

/* --------------------------------------------------- stage 5: medication -- */

function MedicationStage({ result }: { result: WorkupResult }) {
  const m = result.medication;
  const available = m.availability === "AVAILABLE";

  return (
    <section className={`card p-6 ${available ? "" : "border-navy-950/10"}`}>
      <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
        <Pill className="size-3.5" /> Step 5 &middot; Medication
      </h2>

      {!available ? (
        <div
          className={`rounded-xl border p-5 ${
            m.availability === "NOT_INDICATED"
              ? "border-warning/40 bg-warning/5"
              : "border-error/40 bg-error/5"
          }`}
        >
          <p className="flex items-center gap-2 text-sm font-bold">
            <AlertTriangle className="size-4 text-warning" />
            {m.availability.replace(/_/g, " ")}
          </p>
          <p className="mt-2 text-sm text-muted">{m.reason}</p>
          {m.classification_gate && (
            <p className="mt-3 text-xs text-muted">
              This is the governance rule working as intended: therapy runs only after the
              deterministic classification supports it.
            </p>
          )}
        </div>
      ) : (
        <>
          {m.caution && (
            <p className="mb-4 flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              {m.caution}
            </p>
          )}

          <p className="mb-3 text-xs text-muted">
            Ranked for{" "}
            <span className="mono font-semibold text-fg">
              {m.query?.gene} · {m.query?.variant} · {m.query?.disease}
            </span>
          </p>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[620px] text-left text-sm">
              <thead className="text-[10px] uppercase tracking-widest text-muted">
                <tr className="border-b border-navy-950/8">
                  <th className="pb-2 pr-3 font-semibold">#</th>
                  <th className="pb-2 pr-3 font-semibold">Drug</th>
                  <th className="pb-2 pr-3 font-semibold">Response</th>
                  <th className="pb-2 pr-3 font-semibold">Evidence</th>
                  <th className="pb-2 pr-3 font-semibold">Studies</th>
                  <th className="pb-2 font-semibold">Score</th>
                </tr>
              </thead>
              <tbody>
                {m.recommendations.map((r) => (
                  <tr key={r.drug} className="border-b border-navy-950/5 last:border-0">
                    <td className="mono py-2 pr-3 text-muted">{r.rank}</td>
                    <td className="py-2 pr-3 font-semibold capitalize">{r.drug.toLowerCase()}</td>
                    <td className="py-2 pr-3">
                      <span
                        className={`rounded border px-2 py-0.5 text-[10px] font-semibold uppercase ${
                          r.response.toLowerCase() === "sensitivity"
                            ? "border-success/40 bg-success/10 text-success"
                            : "border-error/40 bg-error/10 text-error"
                        }`}
                      >
                        {r.response}
                      </span>
                    </td>
                    <td className="py-2 pr-3">
                      <span className="mono rounded border border-cyan/30 bg-cyan/10 px-2 py-0.5 text-[10px] font-bold text-cyan">
                        {r.evidence_level}
                      </span>
                    </td>
                    <td className="mono py-2 pr-3 text-muted">{r.evidence_count}</td>
                    <td className="py-2">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-20 overflow-hidden rounded-full bg-navy-950/10">
                          <div
                            className="h-full rounded-full bg-cyan"
                            style={{ width: `${Math.min(r.score, 1) * 100}%` }}
                          />
                        </div>
                        <span className="mono text-[10px] text-muted">{r.score.toFixed(3)}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="mt-4 flex items-start gap-2 text-xs text-muted">
            <Info className="mt-0.5 size-3.5 shrink-0 text-cyan" />
            {m.advisory}
          </p>

          {m.token_precision === "GENE_LEVEL" && (
            <p className="mt-2 flex items-start gap-2 text-xs text-warning">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
              This change has no single-residue shorthand, so the ranking leans on gene- and
              disease-level evidence rather than this exact substitution.
            </p>
          )}
        </>
      )}
    </section>
  );
}

/* ------------------------------------------------------- considerations -- */

const CONSIDERATION_TONE: Record<string, string> = {
  guideline: "border-cyan/30 bg-cyan/5",
  counseling: "border-violet/30 bg-violet/5",
  phenotype: "border-success/30 bg-success/5",
  caution: "border-warning/40 bg-warning/5",
  family: "border-violet/30 bg-violet/5",
  pgx: "border-cyan/30 bg-cyan/5",
  disclaimer: "border-navy-950/10 bg-navy-950/[0.03]",
};

function ConsiderationsCard({ result }: { result: WorkupResult }) {
  return (
    <section className="card p-6">
      <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
        <ClipboardList className="size-3.5" /> Clinical considerations
      </h2>
      <ul className="space-y-2">
        {result.considerations.map((c, i) => (
          <li
            key={i}
            className={`rounded-lg border px-4 py-3 text-sm ${
              CONSIDERATION_TONE[c.type] ?? "border-navy-950/10 bg-panel2/40"
            }`}
          >
            <span className="mono mr-2 text-[10px] uppercase tracking-widest text-muted">
              {c.type}
            </span>
            {c.text}
          </li>
        ))}
      </ul>

      <p className="mono mt-4 text-[10px] text-muted">
        sealed · tx {result.provenance.tx_id.slice(0, 18)}… · block #{result.provenance.block_index} ·{" "}
        {result.provenance.model_version}
      </p>
    </section>
  );
}
