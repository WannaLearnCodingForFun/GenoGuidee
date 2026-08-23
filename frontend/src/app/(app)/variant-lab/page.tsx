"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowDown,
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Database,
  FileUp,
  FlaskConical,
  Loader2,
  Scale,
  ShieldCheck,
  Sparkles,
  X,
  XCircle,
} from "lucide-react";
import {
  api,
  type AcmgCriterion,
  type AnalyzeResult,
  type AnnotationCompleteness,
  type ClinicalPatient,
} from "@/lib/api";
import { listAllAccessibleVariants, type AccessibleVariant } from "@/lib/uploads";
import { useAccount } from "@/lib/useAccount";
import { variantLabel } from "@/lib/vcf";
import { classColor, formatAf, shortHash } from "@/lib/ui";

const STAGES = [
  "PARSING VARIANT",
  "GENERATING ESM-2 REPRESENTATION",
  "XGBOOST CLASSIFICATION",
  "EVALUATING ACMG EVIDENCE",
  "RECONCILING EVIDENCE",
  "VERIFYING PROVENANCE",
];

const PROB_ROWS: { key: string; label: string; color: string }[] = [
  { key: "pathogenic", label: "Pathogenic", color: "#ef4444" },
  { key: "likely_pathogenic", label: "Likely Pathogenic", color: "#f59e0b" },
  { key: "vus", label: "VUS", color: "#fda481" },
  { key: "likely_benign", label: "Likely Benign", color: "#b4182d" },
  { key: "benign", label: "Benign", color: "#22c55e" },
];

type Phase = "idle" | "running" | "done";
type Source = "demo" | "uploads";

interface UploadMeta {
  completeness: AnnotationCompleteness;
  missing: { criterion: string; reason: string }[];
  filename: string | null;
}

function VariantLabInner() {
  const searchParams = useSearchParams();
  useAccount();
  const [phase, setPhase] = useState<Phase>("idle");
  const [stageIdx, setStageIdx] = useState(0);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openCriterion, setOpenCriterion] = useState<AcmgCriterion | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  // Uploaded-VCF source
  const [source, setSource] = useState<Source>("uploads");
  const [uploaded, setUploaded] = useState<AccessibleVariant[]>([]);
  const [uploadedId, setUploadedId] = useState<number | null>(null);
  const [loadingUploads, setLoadingUploads] = useState(false);
  const [uploadMeta, setUploadMeta] = useState<UploadMeta | null>(null);
  const [patients, setPatients] = useState<ClinicalPatient[]>([]);
  const [candidatePatientId, setCandidatePatientId] = useState<number | null>(null);
  const [geneQuery, setGeneQuery] = useState("BRCA1");
  const [curated, setCurated] = useState<Array<{
    gene: string; chrom: string; pos: number; ref: string; alt: string;
    label?: string; disclaimer: string;
  }>>([]);
  const [curatedIdx, setCuratedIdx] = useState(0);
  const [curatedNote, setCuratedNote] = useState<string | null>(null);
  const [loadingCurated, setLoadingCurated] = useState(false);

  useEffect(() => {
    api.clinicalPatients()
      .then((rows) => {
        setPatients(rows);
        setCandidatePatientId(rows[0]?.id ?? null);
      })
      .catch(() => setPatients([]));
    return () => timers.current.forEach(clearTimeout);
  }, []);

  // Deep links from the upload tracker: ?source=uploads&variant=<row id>
  useEffect(() => {
    if (searchParams.get("source") === "uploads") setSource("uploads");
    const v = searchParams.get("variant");
    if (v && Number.isFinite(Number(v))) setUploadedId(Number(v));
  }, [searchParams]);

  useEffect(() => {
    if (source !== "uploads" || uploaded.length) return;
    setLoadingUploads(true);
    listAllAccessibleVariants()
      .then((rows) => {
        setUploaded(rows);
        setUploadedId((cur) => cur ?? rows[0]?.id ?? null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load uploaded variants."))
      .finally(() => setLoadingUploads(false));
  }, [source, uploaded.length]);

  const selectedCurated = curated[curatedIdx] ?? null;
  const selectedUploaded = uploaded.find((v) => v.id === uploadedId) ?? null;
  const canRun = source === "demo" ? !!selectedCurated : !!selectedUploaded;

  function runAnalysis() {
    if (phase === "running") return;
    setPhase("running");
    setResult(null);
    setError(null);
    setOpenCriterion(null);
    setUploadMeta(null);
    setStageIdx(0);
    timers.current.forEach(clearTimeout);
    timers.current = [];

    const persistedId = source === "uploads" && selectedUploaded ? selectedUploaded.id : 0;
    const request = (
      source === "demo" && selectedCurated
        ? api.clinicalInterpretCurated({
            chromosome: String(selectedCurated.chrom),
            position: Number(selectedCurated.pos),
            reference: String(selectedCurated.ref),
            alternate: String(selectedCurated.alt),
            gene: selectedCurated.gene,
            patient_id: candidatePatientId ?? undefined,
          })
        : api.clinicalInterpret(persistedId)
    ).then((res) => {
      const acmg = (res.acmg ?? {}) as Record<string, unknown>;
      const ml = (res.ml ?? {}) as Record<string, unknown>;
      const recon = (res.reconciliation ?? {}) as Record<string, unknown>;
      const variant = (res.variant ?? {}) as Record<string, unknown>;
      const criteria = Array.isArray(acmg.criteria) ? (acmg.criteria as AcmgCriterion[]) : [];
      setUploadMeta({
        completeness: {
          present: criteria.filter((c) => c.met).length,
          total: criteria.length || 1,
          percent: 0,
          level: "PARTIAL",
          fields: {},
        },
        missing: [],
        filename: selectedUploaded?.upload?.filename ?? null,
      });
      return {
        variant: {
          id: String(variant.id ?? persistedId),
          gene: String(variant.gene ?? selectedUploaded?.gene ?? "—"),
          transcript: String(variant.transcript ?? ""),
          hgvs_c: String(variant.hgvs_c ?? variant.normalized_variant ?? ""),
          hgvs_p: String(variant.hgvs_p ?? ""),
          chrom: String(variant.chromosome ?? selectedUploaded?.chrom ?? ""),
          pos: Number(variant.position ?? selectedUploaded?.pos ?? 0),
          consequence: String(variant.consequence ?? ""),
          gnomad_af: 0,
          cadd: null,
          revel: null,
          spliceai: null,
          phylop: null,
          hotspot_domain: null,
          functional_evidence: null,
          condition: "",
          inheritance: "",
          showcase: false,
          showcase_label: null,
          public_note: "",
        },
        esm2: {
          mode: String((ml.esm2 as { mode?: string } | undefined)?.mode ?? "unavailable"),
          model: String((ml.esm2 as { model?: string } | undefined)?.model ?? "esm2_t6_8M_UR50D"),
          dims: Number((ml.esm2 as { dims?: number } | undefined)?.dims ?? 0),
          embedding_preview: ((ml.esm2 as { embedding_preview?: number[] } | undefined)?.embedding_preview) ?? [],
          delta_score: Number((ml.esm2 as { delta_score?: number } | undefined)?.delta_score ?? 0),
        },
        ml: {
          probabilities: (ml.probabilities as Record<string, number>) ?? {},
          top_class: String(ml.predicted_class_label ?? ml.top_class ?? "not computed"),
          top_class_key: String(ml.predicted_class ?? ml.top_class_key ?? ""),
          confidence: typeof ml.confidence === "number" ? ml.confidence : 0,
          engine: String(ml.model_name ?? ml.engine ?? ""),
          model_version: String(ml.model_version ?? ""),
        },
        acmg: {
          criteria,
          met: criteria.filter((c) => c.met),
          classification: String(acmg.classification ?? "NOT_EVALUABLE"),
          met_criteria: (acmg.met_criteria as string[]) ?? [],
          rule_note: String(acmg.rule_note ?? ""),
          framework: String(acmg.framework ?? "ACMG/AMP 2015"),
        },
        reconciliation: {
          status: recon.status === "DISCORDANT" ? "DISCORDANT" : recon.status === "CONCORDANT" ? "CONCORDANT" : "DISCORDANT",
          confidence: String(recon.confidence ?? ml.calibration ?? ""),
          ml_bucket: String(ml.top_class ?? ""),
          acmg_bucket: String(acmg.classification ?? ""),
          final_classification: String(recon.final_classification ?? acmg.classification ?? "NOT_EVALUABLE"),
          authority: String(recon.authority ?? "ACMG/AMP (ML never overrides)"),
          note: String(recon.note ?? (recon.disagreement ? "Model/ACMG disagreement" : "")),
        },
        provenance: {
          recorded: true,
          contract: "ClinicalContract",
          tx_id: "clinical",
          block_index: 0,
          interpretation_hash: "",
          patient_hash: "",
          model_version: String(ml.model_version ?? ""),
          evidence_version: String(acmg.framework ?? ""),
          timestamp: Date.now() / 1000,
        },
        mode: "CLINICAL",
        observation_status: String(
          res.observation_status
          ?? (source === "demo"
            ? "CANDIDATE VARIANT — NOT CONFIRMED IN PATIENT"
            : "PATIENT OBSERVED VARIANT"),
        ),
        source_type: String(res.source_type ?? (source === "demo" ? "CURATED_DATASET" : "UPLOADED_VCF")),
      } as AnalyzeResult;
    });

    STAGES.forEach((_, i) => {
      timers.current.push(setTimeout(() => setStageIdx(i), i * 520));
    });
    timers.current.push(
      setTimeout(async () => {
        try {
          const res = await request;
          setResult(res);
          setPhase("done");
        } catch (e) {
          setError(
            e instanceof Error && e.message.includes("failed (")
              ? `Analysis failed — ${e.message}`
              : "Analysis failed — is the backend running on port 8000?",
          );
          setPhase("idle");
        }
      }, STAGES.length * 520 + 200),
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-8 py-10">
      <header className="mb-8">
        <h1 className="flex items-center gap-3 text-2xl font-bold tracking-tight">
          <FlaskConical className="size-6 text-cyan" />
          Variant Lab
        </h1>
        <p className="mt-1 text-sm text-muted">
          Dual-path interpretation: AI pathogenicity prediction beside an independent ACMG/AMP
          rule engine. The AI can never override the evidence.
        </p>
      </header>

      {/* Source toggle */}
      <div className="mb-4 inline-flex rounded-xl border border-navy-950/10 bg-panel2/60 p-1">
        {([
          { id: "demo" as Source, label: "Curated catalog", icon: Database },
          { id: "uploads" as Source, label: "Patient observed", icon: FileUp },
        ]).map((opt) => (
          <button
            key={opt.id}
            onClick={() => {
              setSource(opt.id);
              setError(null);
            }}
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              source === opt.id
                ? "border border-cyan/40 bg-cyan/10 text-cyan"
                : "border border-transparent text-muted hover:text-fg"
            }`}
          >
            <opt.icon className="size-4" />
            {opt.label}
            {opt.id === "uploads" && uploaded.length > 0 && (
              <span className="rounded-full bg-cyan/15 px-1.5 text-[10px] tabular-nums">
                {uploaded.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Case selection */}
      <section className="card p-5">
        {source === "demo" ? (
          <>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
              Curated ClinVar catalog
            </h2>
            <p className="mb-3 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
              CANDIDATE VARIANT — NOT CONFIRMED IN PATIENT. Searching the catalog does not mean the
              patient carries the variant.
            </p>
            <div className="flex flex-wrap items-end gap-3">
              {patients.length > 0 && (
                <label className="text-xs uppercase tracking-widest text-muted">
                  Phenotype context
                  <select
                    value={candidatePatientId ?? ""}
                    onChange={(e) => setCandidatePatientId(e.target.value ? Number(e.target.value) : null)}
                    className="mt-1 block min-w-56 rounded-lg border border-navy-950/15 bg-panel2 px-3 py-2 text-sm normal-case tracking-normal outline-none"
                  >
                    {patients.map((p) => (
                      <option key={p.id} value={p.id}>{p.identifier}</option>
                    ))}
                  </select>
                </label>
              )}
              <label className="text-xs uppercase tracking-widest text-muted">
                Gene
                <input
                  value={geneQuery}
                  onChange={(e) => setGeneQuery(e.target.value.toUpperCase())}
                  className="mt-1 block w-32 rounded-lg border border-navy-950/15 bg-panel2 px-3 py-2 text-sm normal-case tracking-normal outline-none"
                />
              </label>
              <button
                type="button"
                onClick={() => {
                  setLoadingCurated(true);
                  api.clinicalCurated(geneQuery)
                    .then((d) => {
                      setCurated(d.items ?? []);
                      setCuratedNote(d.reason ?? d.disclaimer);
                      setCuratedIdx(0);
                    })
                    .catch((e) => setError(e instanceof Error ? e.message : "Catalog search failed"))
                    .finally(() => setLoadingCurated(false));
                }}
                className="rounded-lg border border-cyan/40 bg-cyan/10 px-4 py-2 text-sm font-semibold text-cyan"
              >
                Search catalog
              </button>
              {candidatePatientId && (
                <button
                  type="button"
                  onClick={() => {
                    setLoadingCurated(true);
                    api.clinicalCandidates(candidatePatientId)
                      .then((d) => {
                        setCurated(
                          (d.items ?? []).map((item) => ({
                            gene: String(item.gene ?? geneQuery),
                            chrom: String(item.chrom ?? ""),
                            pos: Number(item.pos ?? 0),
                            ref: String(item.ref ?? ""),
                            alt: String(item.alt ?? ""),
                            label: String(item.label ?? ""),
                            disclaimer: String(item.disclaimer ?? d.disclaimer),
                          })),
                        );
                        setCuratedNote(d.disclaimer);
                        setCuratedIdx(0);
                      })
                      .finally(() => setLoadingCurated(false));
                  }}
                  className="rounded-lg border border-navy-950/15 px-4 py-2 text-sm"
                >
                  Phenotype candidates
                </button>
              )}
            </div>
            {loadingCurated && <p className="mt-3 text-sm text-muted">Searching ClinVar catalog…</p>}
            {curatedNote && !loadingCurated && curated.length === 0 && (
              <p className="mt-3 text-sm text-muted">{curatedNote}</p>
            )}
            {curated.length > 0 && (
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <select
                  value={curatedIdx}
                  onChange={(e) => setCuratedIdx(Number(e.target.value))}
                  className="min-w-96 rounded-lg border border-navy-950/15 bg-panel2 px-3 py-2 text-sm outline-none"
                >
                  {curated.map((v, i) => (
                    <option key={`${v.gene}-${v.pos}-${i}`} value={i}>
                      {v.gene} {v.chrom}:{v.pos} {v.ref}&gt;{v.alt} {v.label ? `(${v.label})` : ""}
                    </option>
                  ))}
                </select>
                <RunButton phase={phase} disabled={phase === "running" || !canRun} onClick={runAnalysis} />
              </div>
            )}
          </>
        ) : (
          <>
            <h2 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
              <FileUp className="size-3.5" /> Patient observed variants
            </h2>

            {loadingUploads ? (
              <p className="flex items-center gap-2 py-6 text-sm text-muted">
                <Loader2 className="size-4 animate-spin" /> Loading your uploaded variants&hellip;
              </p>
            ) : uploaded.length === 0 ? (
              <div className="flex flex-col items-start gap-2 py-6">
                <p className="text-sm font-medium">No uploaded variants yet</p>
                <p className="text-sm text-muted">
                  Upload a patient VCF and its variants become analyzable here, through the same
                  pipeline as the curated cases.
                </p>
                <Link
                  href="/upload"
                  className="mt-2 inline-flex items-center gap-2 rounded-xl border border-cyan/40 bg-cyan/10 px-5 py-2.5 text-sm font-semibold text-cyan transition-colors hover:bg-cyan/20"
                >
                  <FileUp className="size-4" />
                  Go to Upload &amp; Tracker
                  <ChevronRight className="size-3.5" />
                </Link>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-3">
                <label className="text-xs uppercase tracking-widest text-muted">
                  Select variant ({uploaded.length} available)
                </label>
                <select
                  value={uploadedId ?? ""}
                  onChange={(e) => setUploadedId(Number(e.target.value))}
                  className="min-w-96 rounded-lg border border-navy-950/15 bg-panel2 px-3 py-2 text-sm outline-none focus:border-cyan/50"
                >
                  {uploaded.map((v) => (
                    <option key={v.id} value={v.id}>
                      {variantLabel(v)} ({v.consequence ?? "unannotated"}) &mdash; {v.upload?.filename ?? "file"}
                    </option>
                  ))}
                </select>

                <RunButton phase={phase} disabled={phase === "running" || !canRun} onClick={runAnalysis} />

                {selectedUploaded && (
                  <p className="mono w-full text-[11px] text-muted">
                    {selectedUploaded.chrom}:{selectedUploaded.pos} {selectedUploaded.ref}&gt;
                    {selectedUploaded.alt}
                    {selectedUploaded.transcript ? ` \u00b7 ${selectedUploaded.transcript}` : ""}
                    {selectedUploaded.upload ? ` \u00b7 from ${selectedUploaded.upload.filename}` : ""}
                  </p>
                )}
              </div>
            )}
          </>
        )}
        {error && <p className="mt-3 text-sm text-error">{error}</p>}
      </section>

      {/* Stage animation */}
      <AnimatePresence>
        {phase === "running" && (
          <motion.section
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="card card-glow-cyan mt-6 p-6">
              <div className="grid gap-2 md:grid-cols-6">
                {STAGES.map((s, i) => {
                  const done = i < stageIdx;
                  const current = i === stageIdx;
                  return (
                    <div
                      key={s}
                      className={`flex flex-col items-center gap-2 rounded-lg border p-3 text-center transition-all ${
                        current
                          ? "border-cyan/50 bg-cyan/10"
                          : done
                            ? "border-success/30 bg-success/5"
                            : "border-navy-950/8 opacity-40"
                      }`}
                    >
                      {done ? (
                        <CheckCircle2 className="size-4 text-success" />
                      ) : current ? (
                        <Loader2 className="size-4 animate-spin text-cyan" />
                      ) : (
                        <CircleDot className="size-4 text-muted" />
                      )}
                      <span className="text-[9px] font-semibold leading-tight tracking-wider">
                        {s}
                      </span>
                    </div>
                  );
                })}
              </div>
              <div className="mt-4 h-1 overflow-hidden rounded-full bg-navy-950/5">
                <motion.div
                  className="h-full bg-gradient-to-r from-cyan to-violet"
                  animate={{ width: `${((stageIdx + 1) / STAGES.length) * 100}%` }}
                  transition={{ ease: "easeOut" }}
                />
              </div>
            </div>
          </motion.section>
        )}
      </AnimatePresence>

      {/* Results */}
      <AnimatePresence>
        {phase === "done" && result && (
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            {result.observation_status && (
              <p className={`mt-6 rounded-lg border px-3 py-2 text-xs font-semibold ${
                result.source_type === "CURATED_DATASET"
                  ? "border-warning/30 bg-warning/10 text-warning"
                  : "border-cyan/30 bg-cyan/10 text-cyan"
              }`}>
                {result.observation_status}
              </p>
            )}
            <VariantSummary result={result} />
            {uploadMeta && <UploadEvidenceNotice meta={uploadMeta} />}
            <div className="mt-6 grid gap-5 lg:grid-cols-[1fr_320px_1fr]">
              <AiPath result={result} />
              <Verdict result={result} />
              <AcmgPath result={result} onOpen={setOpenCriterion} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Criterion detail modal */}
      <AnimatePresence>
        {openCriterion && (
          <CriterionModal criterion={openCriterion} onClose={() => setOpenCriterion(null)} />
        )}
      </AnimatePresence>
    </div>
  );
}

function RunButton({
  phase,
  disabled,
  onClick,
}: {
  phase: Phase;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="ml-auto inline-flex items-center gap-2 rounded-xl border border-cyan/50 bg-cyan/15 px-6 py-2.5 text-sm font-bold tracking-wide text-cyan transition-all hover:bg-cyan/25 hover:shadow-[0_0_28px_-6px_#b4182d] disabled:cursor-not-allowed disabled:opacity-50"
    >
      {phase === "running" ? (
        <Loader2 className="size-4 animate-spin" />
      ) : (
        <Sparkles className="size-4" />
      )}
      ANALYZE VARIANT
    </button>
  );
}

/**
 * Uploaded variants carry only the evidence their VCF annotations provide.
 * Saying so explicitly matters: a VUS here may mean "genuinely uncertain" or
 * merely "half the criteria could not be evaluated", and those are very
 * different clinical situations.
 */
function UploadEvidenceNotice({ meta }: { meta: UploadMeta }) {
  const { completeness, missing } = meta;
  const tone =
    completeness.level === "HIGH"
      ? "border-success/35 bg-success/5"
      : completeness.level === "PARTIAL"
        ? "border-warning/40 bg-warning/5"
        : "border-error/40 bg-error/5";

  return (
    <section className={`card mt-4 border p-5 ${tone}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.25em]">
          <FileUp className="size-3.5" />
          Uploaded variant &middot; evidence available
        </h3>
        <span className="text-xs text-muted">
          {meta.filename ? `from ${meta.filename} \u00b7 ` : ""}
          annotation completeness{" "}
          <span className="font-bold text-fg">
            {completeness.present}/{completeness.total} ({completeness.percent}%)
          </span>
        </span>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {Object.entries(completeness.fields).map(([field, present]) => (
          <span
            key={field}
            className={`mono rounded border px-2 py-0.5 text-[10px] ${
              present
                ? "border-success/40 bg-success/10 text-success"
                : "border-navy-950/15 bg-navy-950/5 text-muted line-through"
            }`}
          >
            {field}
          </span>
        ))}
      </div>

      <p className="mt-4 text-xs font-semibold uppercase tracking-widest text-muted">
        Criteria that cannot be evaluated from a VCF
      </p>
      <ul className="mt-2 space-y-1.5">
        {missing.map((m) => (
          <li key={m.criterion} className="flex gap-2 text-xs text-muted">
            <span className="mono shrink-0 font-bold text-warning">{m.criterion}</span>
            <span>{m.reason}</span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-muted/80">
        These criteria require curated evidence a VCF does not carry, so they are reported as
        NOT_MET rather than assumed. An uploaded variant therefore classifies more conservatively
        than a curated case with identical annotations.
      </p>
    </section>
  );
}

export default function VariantLab() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl px-8 py-10 text-sm text-muted">Loading Variant Lab&hellip;</div>
      }
    >
      <VariantLabInner />
    </Suspense>
  );
}

function VariantSummary({ result }: { result: AnalyzeResult }) {
  const v = result.variant;
  const cc = classColor(result.reconciliation.final_classification);
  return (
    <section className="card mt-6 flex flex-wrap items-center gap-x-8 gap-y-3 p-5">
      <div>
        <p className="text-lg font-bold">
          {v.gene} <span className="mono text-base font-medium text-cyan">{v.hgvs_c}</span>
        </p>
        <p className="mono text-xs text-muted">
          {v.hgvs_p} · {v.transcript} · chr{v.chrom}:{v.pos.toLocaleString()}
        </p>
      </div>
      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted">
        <div>
          <dt className="uppercase tracking-wider text-muted/60">Consequence</dt>
          <dd className="font-medium text-fg">{v.consequence.replace("_", " ")}</dd>
        </div>
        <div>
          <dt className="uppercase tracking-wider text-muted/60">gnomAD AF</dt>
          <dd className="mono font-medium text-fg">{formatAf(v.gnomad_af)}</dd>
        </div>
        <div>
          <dt className="uppercase tracking-wider text-muted/60">Condition</dt>
          <dd className="font-medium text-fg">{v.condition}</dd>
        </div>
      </dl>
      <span
        className={`ml-auto rounded-lg border px-4 py-2 text-sm font-bold tracking-wide ${cc.border} ${cc.bg} ${cc.text}`}
      >
        {result.reconciliation.final_classification.toUpperCase()}
      </span>
    </section>
  );
}

function AiPath({ result }: { result: AnalyzeResult }) {
  return (
    <section className="card card-glow-violet p-5">
      <h3 className="mb-4 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.25em] text-violet">
        <BrainCircuit className="size-4" /> AI Path
      </h3>

      <div className="space-y-2 text-center">
        <div className="rounded-lg border border-violet/30 bg-violet/5 py-2.5 text-sm font-semibold">
          ESM-2 <span className="mono text-[10px] font-normal text-muted">({result.esm2.model})</span>
        </div>
        <ArrowDown className="mx-auto size-4 text-violet/50" />
        <div className="rounded-lg border border-navy-950/10 bg-panel2 p-3">
          <p className="mb-2 text-xs font-semibold">
            Embedding{" "}
            <span className="mono font-normal text-muted">
              {result.esm2.dims}-dim · Δ-score {result.esm2.delta_score.toFixed(2)}
            </span>
          </p>
          <div className="flex h-6 overflow-hidden rounded">
            {result.esm2.embedding_preview.map((x, i) => {
              const norm = Math.max(0, Math.min(1, (x + 2) / 4));
              return (
                <div
                  key={i}
                  className="flex-1"
                  style={{
                    background: `rgba(${Math.round(139 * (1 - norm))}, ${Math.round(
                      92 + 137 * norm,
                    )}, 255, ${0.25 + norm * 0.75})`,
                  }}
                />
              );
            })}
          </div>
          <p className="mt-1.5 text-[9px] uppercase tracking-widest text-muted">
            first 64 dimensions · {result.esm2.mode}
          </p>
        </div>
        <ArrowDown className="mx-auto size-4 text-violet/50" />
        <div className="rounded-lg border border-violet/30 bg-violet/5 py-2.5 text-sm font-semibold">
          XGBoost{" "}
          <span className="mono text-[10px] font-normal text-muted">({result.ml.engine})</span>
        </div>
      </div>

      <div className="mt-5 space-y-2.5">
        {PROB_ROWS.map((row, i) => {
          const p = result.ml.probabilities[row.key] ?? 0;
          const top = row.key === result.ml.top_class_key;
          return (
            <div key={row.key}>
              <div className="mb-1 flex justify-between text-xs">
                <span className={top ? "font-bold text-fg" : "text-muted"}>{row.label}</span>
                <span className="mono tabular-nums" style={{ color: row.color }}>
                  {(p * 100).toFixed(1)}%
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-navy-950/5">
                <motion.div
                  className="h-full rounded-full"
                  style={{
                    background: row.color,
                    boxShadow: top ? `0 0 12px ${row.color}` : undefined,
                  }}
                  initial={{ width: 0 }}
                  animate={{ width: `${p * 100}%` }}
                  transition={{ delay: 0.2 + i * 0.1, duration: 0.7, ease: "easeOut" }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <p className="mt-4 text-center text-sm">
        Top call:{" "}
        <span className="font-bold text-violet">{result.ml.top_class}</span>{" "}
        <span className="mono text-muted">({(result.ml.confidence * 100).toFixed(1)}%)</span>
      </p>
    </section>
  );
}

function Verdict({ result }: { result: AnalyzeResult }) {
  const concordant = result.reconciliation.status === "CONCORDANT";
  return (
    <section className="flex flex-col gap-4">
      <motion.div
        initial={{ scale: 0.92, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ delay: 0.4, type: "spring", stiffness: 150 }}
        className={`card flex flex-col items-center p-6 text-center ${
          concordant ? "card-glow-success" : "card-glow-warning"
        }`}
      >
        {concordant ? (
          <CheckCircle2 className="size-12 text-success" />
        ) : (
          <AlertTriangle className="size-12 text-warning" />
        )}
        <p
          className={`mt-3 text-xl font-black tracking-widest ${
            concordant ? "text-success" : "text-warning"
          }`}
        >
          {result.reconciliation.status}
        </p>
        <p className="mt-1 text-xs font-bold uppercase tracking-[0.2em] text-muted">
          {result.reconciliation.confidence}
        </p>
        <p className="mt-4 text-xs leading-relaxed text-muted">{result.reconciliation.note}</p>
      </motion.div>

      <div className="card p-4">
        <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted">
          Final classification (ACMG authority)
        </p>
        <p
          className={`mt-1 text-lg font-bold ${classColor(result.reconciliation.final_classification).text}`}
        >
          {result.reconciliation.final_classification}
        </p>
        <p className="mt-2 text-[11px] text-muted">{result.reconciliation.authority}</p>
      </div>

      <div className="card p-4">
        <p className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted">
          <ShieldCheck className="size-3.5 text-cyan" /> Provenance sealed
        </p>
        <dl className="mono space-y-1 text-[10px] text-muted">
          <div className="flex justify-between gap-2">
            <dt>tx</dt>
            <dd className="text-cyan">{shortHash(result.provenance.tx_id, 12)}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt>interpretation</dt>
            <dd>{shortHash(result.provenance.interpretation_hash)}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt>contract</dt>
            <dd className="text-fg">{result.provenance.contract}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt>model</dt>
            <dd>{result.provenance.model_version}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}

function AcmgPath({
  result,
  onOpen,
}: {
  result: AnalyzeResult;
  onOpen: (c: AcmgCriterion) => void;
}) {
  const met = result.acmg.criteria.filter((c) => c.met);
  const notMet = result.acmg.criteria.filter((c) => !c.met);
  return (
    <section className="card card-glow-cyan p-5">
      <h3 className="mb-4 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.25em] text-cyan">
        <Scale className="size-4" /> ACMG Path
      </h3>

      <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-muted">
        Criteria met ({met.length})
      </p>
      <div className="grid grid-cols-2 gap-2">
        {met.map((c, i) => {
          const benign = c.strength.toLowerCase().includes("benign") || c.id.startsWith("B");
          return (
            <motion.button
              key={c.id}
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.25 + i * 0.1 }}
              onClick={() => onOpen(c)}
              className={`group flex items-center justify-between rounded-lg border p-3 text-left transition-all hover:scale-[1.02] ${
                benign
                  ? "border-success/40 bg-success/10 hover:shadow-[0_0_16px_-6px_#22c55e]"
                  : "border-cyan/40 bg-cyan/10 hover:shadow-[0_0_16px_-6px_#b4182d]"
              }`}
            >
              <div>
                <p className={`text-sm font-black ${benign ? "text-success" : "text-cyan"}`}>
                  {c.id}
                </p>
                <p className="text-[9px] uppercase tracking-wider text-muted">{c.strength}</p>
              </div>
              <ChevronRight className="size-4 text-muted transition-transform group-hover:translate-x-0.5" />
            </motion.button>
          );
        })}
        {met.length === 0 && (
          <p className="col-span-2 rounded-lg border border-navy-950/10 p-3 text-xs text-muted">
            No criteria met — insufficient evidence.
          </p>
        )}
      </div>

      <p className="mt-4 mb-2 text-[10px] font-semibold uppercase tracking-widest text-muted">
        Evaluated, not met ({notMet.length})
      </p>
      <div className="flex flex-wrap gap-1.5">
        {notMet.map((c) => (
          <button
            key={c.id}
            onClick={() => onOpen(c)}
            className="rounded border border-navy-950/10 px-2 py-1 text-[10px] text-muted transition-colors hover:border-navy-950/30 hover:text-fg"
          >
            {c.id}
          </button>
        ))}
      </div>

      <div className="mt-5 rounded-lg border border-navy-950/10 bg-panel2 p-3">
        <p className={`text-sm font-bold ${classColor(result.acmg.classification).text}`}>
          {result.acmg.classification}
        </p>
        <p className="mt-1 text-[11px] leading-relaxed text-muted">{result.acmg.rule_note}</p>
      </div>
    </section>
  );
}

function CriterionModal({
  criterion,
  onClose,
}: {
  criterion: AcmgCriterion;
  onClose: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 grid place-items-center bg-bg/70 p-6"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.94, y: 12 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.94, y: 12 }}
        transition={{ type: "spring", stiffness: 260, damping: 24 }}
        onClick={(e) => e.stopPropagation()}
        className="glass w-full max-w-lg rounded-2xl p-6"
      >
        <div className="flex items-start justify-between">
          <div>
            <p className="text-2xl font-black text-cyan">{criterion.id}</p>
            <p className="mt-0.5 text-sm text-fg">{criterion.name}</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg border border-navy-950/10 p-1.5 text-muted hover:text-fg"
          >
            <X className="size-4" />
          </button>
        </div>

        <dl className="mt-5 space-y-4 text-sm">
          <div>
            <dt className="text-[10px] font-semibold uppercase tracking-widest text-muted">
              Strength
            </dt>
            <dd className="mt-0.5 font-medium">{criterion.strength}</dd>
          </div>
          <div>
            <dt className="text-[10px] font-semibold uppercase tracking-widest text-muted">
              Status
            </dt>
            <dd
              className={`mt-1 inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs font-bold ${
                criterion.met
                  ? "bg-success/10 text-success"
                  : "bg-navy-950/5 text-muted"
              }`}
            >
              {criterion.met ? <CheckCircle2 className="size-3.5" /> : <XCircle className="size-3.5" />}
              {criterion.status.replace("_", " ")}
            </dd>
          </div>
          <div>
            <dt className="text-[10px] font-semibold uppercase tracking-widest text-muted">
              Reason
            </dt>
            <dd className="mt-0.5 leading-relaxed text-muted">{criterion.reason}</dd>
          </div>
          <div>
            <dt className="text-[10px] font-semibold uppercase tracking-widest text-muted">
              Evidence source
            </dt>
            <dd className="mt-0.5 leading-relaxed text-muted">{criterion.evidence_source}</dd>
          </div>
        </dl>
      </motion.div>
    </motion.div>
  );
}
