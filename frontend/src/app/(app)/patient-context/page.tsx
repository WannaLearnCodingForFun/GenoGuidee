"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  BookOpenCheck,
  ChevronRight,
  Dna,
  FlaskConical,
  HeartPulse,
  Info,
  Pill,
  ShieldAlert,
  UserRound,
  Users,
} from "lucide-react";
import {
  PolarAngleAxis,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
} from "recharts";
import { api, type ContextAnalysis, type Patient } from "@/lib/api";
import { classColor, levelColor } from "@/lib/ui";
import { useAccount } from "@/lib/useAccount";

// Demo fallback only — used when no authenticated patient context exists.
const DEMO_PATIENT_ID = "G-1027";

const CONSIDERATION_ICONS: Record<string, typeof Info> = {
  guideline: BookOpenCheck,
  counseling: Users,
  phenotype: Activity,
  caution: AlertTriangle,
  pgx: Pill,
  info: Info,
  disclaimer: ShieldAlert,
};

export default function PatientContext() {
  const { account } = useAccount();
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedId, setSelectedId] = useState(DEMO_PATIENT_ID);
  const [context, setContext] = useState<{ patient: Patient; analyses: ContextAnalysis[] } | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api.patients().then(setPatients).catch(() => setError(true));
  }, []);

  useEffect(() => {
    if (account?.role === "patient" && account.id) setSelectedId(account.id);
  }, [account]);

  useEffect(() => {
    setContext(null);
    api.patientContext(selectedId).then(setContext).catch(() => setError(true));
  }, [selectedId]);

  const p = context?.patient;
  const funnel = p
    ? [
        { label: "Total variants", value: p.genome_stats.total_variants },
        { label: "Candidates", value: p.genome_stats.candidates },
        { label: "Annotated", value: p.genome_stats.annotated },
        { label: "Prioritized", value: p.genome_stats.prioritized },
      ]
    : [];

  return (
    <div className="mx-auto max-w-7xl px-8 py-10">
      <header className="mb-6">
        <h1 className="flex items-center gap-3 text-2xl font-bold tracking-tight">
          <UserRound className="size-6 text-cyan" />
          Patient Context
        </h1>
        <p className="mt-1 text-sm text-muted">
          Downstream decision support: variant significance interpreted against phenotype,
          family history and medications.
        </p>
      </header>

      {/* Patient selector */}
      <div className="mb-6 flex flex-wrap gap-2">
        {patients.map((pt) => (
          <button
            key={pt.id}
            onClick={() => setSelectedId(pt.id)}
            className={`rounded-xl border px-4 py-2.5 text-left transition-all ${
              pt.id === selectedId
                ? "border-cyan/50 bg-cyan/10 shadow-[0_0_18px_-8px_#b4182d]"
                : "border-navy-950/10 bg-panel2/60 hover:border-navy-950/25"
            }`}
          >
            <p className="text-sm font-bold">{pt.id}</p>
            <p className="text-[11px] text-muted">
              {pt.age}y {pt.sex} · {pt.diagnosis_short}
            </p>
          </button>
        ))}
      </div>

      {error && (
        <p className="text-sm text-error">Backend not reachable — start the FastAPI server.</p>
      )}

      {p && context && (
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} key={p.id}>
          {/* Demographics + funnel */}
          <div className="grid gap-4 lg:grid-cols-[380px_1fr]">
            <section className="card p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xl font-bold">{p.id}</p>
                  <p className="text-sm text-muted">
                    {p.age} years · {p.sex}
                  </p>
                </div>
                <span className="rounded border border-warning/40 bg-warning/10 px-2 py-1 text-[9px] font-bold uppercase tracking-widest text-warning">
                  {p.label}
                </span>
              </div>
              <dl className="mt-4 space-y-3 text-sm">
                <div>
                  <dt className="text-[10px] font-semibold uppercase tracking-widest text-muted">
                    Diagnosis
                  </dt>
                  <dd className="mt-0.5">{p.diagnosis}</dd>
                </div>
                <div>
                  <dt className="text-[10px] font-semibold uppercase tracking-widest text-muted">
                    Phenotypes (HPO)
                  </dt>
                  <dd className="mt-1.5 flex flex-wrap gap-1.5">
                    {p.phenotypes.map((ph) => (
                      <span
                        key={ph.hpo}
                        className="rounded border border-violet/30 bg-violet/10 px-2 py-0.5 text-[11px] text-violet"
                        title={ph.hpo}
                      >
                        {ph.term}
                      </span>
                    ))}
                  </dd>
                </div>
                <div>
                  <dt className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted">
                    <HeartPulse className="size-3" /> Family history{" "}
                    <span className={p.family_history.positive ? "text-warning" : "text-success"}>
                      {p.family_history.positive ? "POSITIVE" : "NEGATIVE"}
                    </span>
                  </dt>
                  <dd className="mt-1.5 space-y-1 text-xs text-muted">
                    {p.family_history.entries.map((e) => (
                      <p key={e}>· {e}</p>
                    ))}
                  </dd>
                </div>
                <div>
                  <dt className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted">
                    <Pill className="size-3" /> Medications
                  </dt>
                  <dd className="mt-1.5 space-y-1.5">
                    {p.medications.map((m) => (
                      <div key={m.name} className="rounded-lg border border-navy-950/8 bg-panel2 px-3 py-2">
                        <p className="text-xs font-medium">
                          {m.name} <span className="text-muted">— {m.dose}</span>
                        </p>
                        {m.pgx_gene && (
                          <p className="mt-0.5 text-[10px] text-cyan">
                            PGx: {m.pgx_gene} — {m.pgx_note}
                          </p>
                        )}
                      </div>
                    ))}
                  </dd>
                </div>
              </dl>
            </section>

            <div className="flex flex-col gap-4">
              {/* Genome triage funnel */}
              <section className="card card-glow-cyan p-5">
                <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
                  <Dna className="size-4 text-cyan" /> Genome triage funnel
                </h2>
                <div className="flex items-center gap-2">
                  {funnel.map((f, i) => (
                    <div key={f.label} className="flex flex-1 items-center gap-2">
                      <motion.div
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ delay: i * 0.12 }}
                        className="flex-1 rounded-xl border border-navy-950/10 bg-panel2 p-4 text-center"
                        style={{
                          borderColor: i === funnel.length - 1 ? "rgba(180,24,45,0.5)" : undefined,
                          boxShadow: i === funnel.length - 1 ? "0 0 22px -8px #b4182d" : undefined,
                        }}
                      >
                        <p className="text-2xl font-black tabular-nums text-fg">
                          {f.value.toLocaleString()}
                        </p>
                        <p className="mt-1 text-[10px] uppercase tracking-widest text-muted">
                          {f.label}
                        </p>
                      </motion.div>
                      {i < funnel.length - 1 && (
                        <ChevronRight className="size-4 shrink-0 text-cyan/50" />
                      )}
                    </div>
                  ))}
                </div>
              </section>

              {/* Top-line finding */}
              {context.analyses[0] && (
                <section className="card flex items-center gap-6 p-5">
                  <div className="min-w-0">
                    <p className="text-[10px] font-semibold uppercase tracking-widest text-muted">
                      Highest clinical relevance
                    </p>
                    <p className="mt-1 truncate text-lg font-bold">
                      {context.analyses[0].variant.gene}{" "}
                      <span className="mono text-sm font-medium text-cyan">
                        {context.analyses[0].variant.hgvs_c}
                      </span>
                    </p>
                    <p className="text-xs text-muted">{context.analyses[0].gene_disease}</p>
                  </div>
                  <span
                    className={`ml-auto shrink-0 rounded-lg border px-4 py-2 text-sm font-black tracking-widest ${levelColor(
                      context.analyses[0].relevance.level,
                    )}`}
                  >
                    {context.analyses[0].relevance.level}
                  </span>
                </section>
              )}
            </div>
          </div>

          {/* Variant analyses */}
          <div className="mt-6 space-y-5">
            {context.analyses.map((a, i) => (
              <VariantContextCard key={a.variant.id} analysis={a} index={i} />
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}

function VariantContextCard({ analysis: a, index }: { analysis: ContextAnalysis; index: number }) {
  const cc = classColor(a.acmg_classification);
  const gauge = [{ name: "score", value: a.relevance.score, fill: a.relevance.level === "HIGH" ? "#ef4444" : a.relevance.level === "MODERATE" ? "#f59e0b" : "#22c55e" }];

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15 + index * 0.1 }}
      className="card p-5"
    >
      <div className="grid gap-6 lg:grid-cols-[220px_1fr_1fr]">
        {/* Gauge */}
        <div className="flex flex-col items-center">
          <div className="relative h-40 w-40">
            <ResponsiveContainer width="100%" height="100%">
              <RadialBarChart
                innerRadius="72%"
                outerRadius="100%"
                data={gauge}
                startAngle={220}
                endAngle={-40}
              >
                <PolarAngleAxis type="number" domain={[0, 100]} tick={false} axisLine={false} />
                <RadialBar dataKey="value" cornerRadius={8} background={{ fill: "rgba(255,255,255,0.05)" }} />
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <p className="text-3xl font-black tabular-nums">{a.relevance.score}</p>
              <p className="text-[9px] uppercase tracking-widest text-muted">relevance</p>
            </div>
          </div>
          <span
            className={`rounded-lg border px-3 py-1 text-xs font-black tracking-widest ${levelColor(a.relevance.level)}`}
          >
            {a.relevance.level}
          </span>
        </div>

        {/* Identity + components */}
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-base font-bold">
              {a.variant.gene}{" "}
              <span className="mono text-sm font-medium text-cyan">{a.variant.hgvs_c}</span>
            </p>
            <span className={`rounded border px-2 py-0.5 text-[10px] font-bold ${cc.border} ${cc.bg} ${cc.text}`}>
              ACMG: {a.acmg_classification}
            </span>
            <span className="rounded border border-violet/30 bg-violet/10 px-2 py-0.5 text-[10px] font-bold text-violet">
              AI: {a.ml_top_class} {(a.ml_confidence * 100).toFixed(0)}%
            </span>
          </div>
          <p className="mt-1 text-xs text-muted">
            {a.gene_disease ?? a.variant.condition}
            {a.phenotype_matched_terms.length > 0 && (
              <span className="text-success">
                {" "}· phenotype match: {a.phenotype_matched_terms.join(", ")}
              </span>
            )}
          </p>

          <div className="mt-4 space-y-2">
            {a.relevance.components.map((c) => (
              <div key={c.name}>
                <div className="mb-0.5 flex justify-between text-[11px]">
                  <span className="text-muted">{c.name}</span>
                  <span className="mono tabular-nums text-fg">
                    {c.value}/{c.max}
                  </span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-navy-950/5">
                  <motion.div
                    className="h-full rounded-full bg-gradient-to-r from-cyan to-violet"
                    initial={{ width: 0 }}
                    animate={{ width: `${(c.value / c.max) * 100}%` }}
                    transition={{ duration: 0.7, delay: 0.3 }}
                  />
                </div>
              </div>
            ))}
          </div>

          <div className="mt-3 flex flex-wrap gap-1.5">
            {a.acmg_met.map((m) => (
              <span
                key={m}
                className="mono rounded border border-cyan/25 bg-cyan/5 px-1.5 py-0.5 text-[10px] text-cyan"
              >
                {m}
              </span>
            ))}
          </div>
        </div>

        {/* Considerations */}
        <div>
          <h4 className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted">
            <FlaskConical className="size-3.5 text-cyan" /> Clinical considerations
            (evidence-grounded)
          </h4>
          <ul className="space-y-2">
            {a.considerations.map((c, i) => {
              const Icon = CONSIDERATION_ICONS[c.type] ?? Info;
              const tone =
                c.type === "caution"
                  ? "border-warning/30 bg-warning/5"
                  : c.type === "pgx"
                    ? "border-cyan/25 bg-cyan/5"
                    : c.type === "disclaimer"
                      ? "border-navy-950/8 bg-navy-950/2"
                      : "border-navy-950/10 bg-panel2";
              return (
                <li key={i} className={`flex gap-2.5 rounded-lg border p-2.5 text-[11px] leading-relaxed text-muted ${tone}`}>
                  <Icon className="mt-0.5 size-3.5 shrink-0 text-cyan" />
                  {c.text}
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </motion.section>
  );
}
