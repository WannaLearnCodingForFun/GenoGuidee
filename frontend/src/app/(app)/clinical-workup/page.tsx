"use client";

import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  ArrowRight,
  BrainCircuit,
  ClipboardList,
  Dna,
  FileUp,
  FlaskConical,
  GitMerge,
  Loader2,
  Pill,
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
import { WorkupStages } from "@/components/WorkupStages";
import { listAllAccessibleVariants, type AccessibleVariant } from "@/lib/uploads";
import { variantLabel } from "@/lib/vcf";

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
  const [source, setSource] = useState<Source>("upload");
  const [curated, setCurated] = useState<VariantListItem[]>([]);
  const [curatedId, setCuratedId] = useState("VAR-BRCA1-5266DUP");
  const [uploaded, setUploaded] = useState<AccessibleVariant[]>([]);
  const [uploadedId, setUploadedId] = useState<number | null>(null);
  const [loadingUploads, setLoadingUploads] = useState(false);

  const [history, setHistory] = useState<PatientHistory>(EMPTY_HISTORY);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<WorkupResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [persistedId, setPersistedId] = useState<string | null>(null);
  const [patientIdentifier, setPatientIdentifier] = useState("");
  const [lookup, setLookup] = useState<{
    identifier: string;
    full_name: string | null;
    email: string | null;
  } | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [accountStatus, setAccountStatus] = useState<string | null>(null);

  useEffect(() => {
    api.variants()
      .then((rows) => {
        setCurated(rows);
        setCuratedId((prev) => (
          rows.some((v) => v.id === prev) ? prev : (rows.find((v) => v.showcase)?.id ?? rows[0]?.id ?? prev)
        ));
      })
      .catch(() => setCurated([]));
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
  const canRun = history.consent_confirmed && Boolean(patientIdentifier.trim());

  async function confirmPatientId() {
    const ident = patientIdentifier.trim();
    if (!ident) {
      setLookup(null);
      setLookupError(null);
      return;
    }
    try {
      const row = await api.clinicalLookupPatient(ident);
      setLookup(row);
      setLookupError(null);
    } catch (e) {
      setLookup(null);
      setLookupError(e instanceof Error ? e.message : "Patient ID not found.");
    }
  }

  function set<K extends keyof PatientHistory>(key: K, value: PatientHistory[K]) {
    setHistory((h) => ({ ...h, [key]: value }));
  }

  async function run() {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const persisted = await api.clinicalWorkup({
        ...history,
        variant_id: source === "upload" && selectedUploaded ? Number(selectedUploaded.id) : null,
        patient_identifier: patientIdentifier.trim(),
      });
      let res: WorkupResult | null = null;
      if (source === "upload" && selectedUploaded) {
        res = await api.workup({
          variant_id: null,
          uploaded_variant: {
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
          },
          history,
          subject_ref: persisted.patient.identifier,
        });
        setResult(res);
      } else if (source === "curated" && curatedId) {
        res = await api.workup({
          variant_id: curatedId,
          history,
          subject_ref: persisted.patient.identifier,
        });
        setResult(res);
      }
      if (res && persisted.patient.id) {
        await api.clinicalSaveWorkupResult(persisted.patient.id, res);
      }
      setError(null);
      setPersistedId(persisted.patient.identifier);
      setAccountStatus(persisted.patient.account_status ?? "active");
      if (source === "curated" && curatedId && persisted.patient.id) {
        try {
          const detail = await api.variant(curatedId);
          if (detail.ref && detail.alt) {
            await api.clinicalInterpretCurated({
              chromosome: detail.chrom,
              position: detail.pos,
              reference: detail.ref,
              alternate: detail.alt,
              gene: detail.gene,
              patient_id: persisted.patient.id,
            });
          }
        } catch {
          /* stages already rendered; report persist is best-effort */
        }
      }
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
            Enter the Patient ID issued when the patient created their account, then record
            history alongside a variant. The workup runs gene &middot; variant &middot; disease,
            classification, AI/ACMG reconciliation, then a medication shortlist gated on the verdict.
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
                { id: "curated" as Source, label: "Persisted variant", icon: FlaskConical },
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
              <div className="max-w-xl">
                <select
                  value={curatedId}
                  onChange={(e) => setCuratedId(e.target.value)}
                  className="w-full rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none focus:border-cyan/50"
                >
                  {curated.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.gene} {v.hgvs_c} ({v.consequence})
                      {v.showcase_label ? ` — ${v.showcase_label}` : ""}
                    </option>
                  ))}
                </select>
                <p className="mt-2 text-[11px] text-muted">
                  CANDIDATE VARIANT — NOT CONFIRMED IN PATIENT. Catalog entries are literature/ClinVar records, not an observed patient call.
                </p>
              </div>
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

          <div className="mb-4">
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-muted">
              Patient ID
            </label>
            <input
              value={patientIdentifier}
              onChange={(e) => {
                setPatientIdentifier(e.target.value.toUpperCase());
                setLookup(null);
                setLookupError(null);
              }}
              onBlur={() => { void confirmPatientId(); }}
              className="w-full max-w-xl rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 font-mono text-sm outline-none focus:border-cyan/50"
              placeholder="PAT-2026-000001"
              autoComplete="off"
            />
            <p className="mt-1 text-[11px] text-muted">
              Required. Issued when the patient signs up. Doctors cannot create a new Patient ID here.
            </p>
            {lookup && (
              <p className="mt-2 text-sm text-success">
                Registered account: <span className="font-semibold">{lookup.full_name || lookup.identifier}</span>
                {lookup.email ? <span className="text-muted"> · {lookup.email}</span> : null}
              </p>
            )}
            {lookupError && (
              <p className="mt-2 text-sm text-error">{lookupError}</p>
            )}
          </div>

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
            {!patientIdentifier.trim() ? (
              <span className="text-xs text-muted">Enter the patient&apos;s account Patient ID to enable the run.</span>
            ) : !history.consent_confirmed ? (
              <span className="text-xs text-muted">Confirm consent to enable the run.</span>
            ) : null}
          </div>

          {error && (
            <p className="mt-4 flex items-center gap-2 text-sm text-error">
              <XCircle className="size-4" /> {error}
            </p>
          )}
          {persistedId && (
            <div className="mt-4 space-y-2 rounded-xl border border-success/30 bg-success/5 p-3 text-sm">
              <p className="text-success">
                Linked to Patient ID: <span className="font-mono font-semibold">{persistedId}</span>
                {accountStatus && (
                  <span className="ml-2 rounded border border-navy-950/10 px-2 py-0.5 text-[10px] uppercase tracking-widest">
                    {accountStatus}
                  </span>
                )}
              </p>
              <p className="text-xs text-muted">
                Same ID the patient uses at login. Clinical notes were saved on that account.
              </p>
            </div>
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
              <WorkupStages result={result} />
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
