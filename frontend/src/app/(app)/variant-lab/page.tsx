"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowDown,
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  CircleDot,
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
  type VariantListItem,
} from "@/lib/api";
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

export default function VariantLab() {
  const [variants, setVariants] = useState<VariantListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string>("VAR-BRCA1-5266DUP");
  const [phase, setPhase] = useState<Phase>("idle");
  const [stageIdx, setStageIdx] = useState(0);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openCriterion, setOpenCriterion] = useState<AcmgCriterion | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    api.variants().then(setVariants).catch(() => setError("Backend not reachable."));
    return () => timers.current.forEach(clearTimeout);
  }, []);

  const showcase = useMemo(() => variants.filter((v) => v.showcase), [variants]);
  const selected = variants.find((v) => v.id === selectedId);

  function runAnalysis() {
    if (phase === "running") return;
    setPhase("running");
    setResult(null);
    setError(null);
    setOpenCriterion(null);
    setStageIdx(0);
    timers.current.forEach(clearTimeout);
    timers.current = [];

    const request = api.analyze(selectedId, "G-1027");

    STAGES.forEach((_, i) => {
      timers.current.push(setTimeout(() => setStageIdx(i), i * 520));
    });
    timers.current.push(
      setTimeout(async () => {
        try {
          const res = await request;
          setResult(res);
          setPhase("done");
        } catch {
          setError("Analysis failed — is the backend running on port 8000?");
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

      {/* Case selection */}
      <section className="card p-5">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
          Showcase cases
        </h2>
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          {showcase.map((v) => {
            const active = v.id === selectedId;
            return (
              <button
                key={v.id}
                onClick={() => setSelectedId(v.id)}
                className={`rounded-xl border p-3 text-left transition-all ${
                  active
                    ? "border-cyan/50 bg-cyan/10 shadow-[0_0_20px_-8px_#b4182d]"
                    : "border-navy-950/10 bg-panel2/60 hover:border-navy-950/25"
                }`}
              >
                <p className="text-sm font-semibold">
                  {v.gene} <span className="mono text-xs font-normal text-muted">{v.hgvs_c}</span>
                </p>
                <p className="mt-1 line-clamp-2 text-[11px] text-muted">{v.showcase_label}</p>
              </button>
            );
          })}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <label className="text-xs uppercase tracking-widest text-muted">
            Full demo dataset ({variants.length} variants)
          </label>
          <select
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
            className="min-w-72 rounded-lg border border-navy-950/15 bg-panel2 px-3 py-2 text-sm outline-none focus:border-cyan/50"
          >
            {variants.map((v) => (
              <option key={v.id} value={v.id}>
                {v.gene} {v.hgvs_c} ({v.consequence})
              </option>
            ))}
          </select>

          <button
            onClick={runAnalysis}
            disabled={phase === "running" || !selected}
            className="ml-auto inline-flex items-center gap-2 rounded-xl border border-cyan/50 bg-cyan/15 px-6 py-2.5 text-sm font-bold tracking-wide text-cyan transition-all hover:bg-cyan/25 hover:shadow-[0_0_28px_-6px_#b4182d] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {phase === "running" ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Sparkles className="size-4" />
            )}
            ANALYZE VARIANT
          </button>
        </div>
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
            <VariantSummary result={result} />
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
