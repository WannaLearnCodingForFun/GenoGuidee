"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { motion } from "framer-motion";
import {
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  FileText,
  FlaskConical,
  GitMerge,
  Link2,
  Network,
  Scale,
  ShieldCheck,
  Stethoscope,
  UserRound,
  Users,
  Dna,
  AlertTriangle,
  BadgeCheck,
} from "lucide-react";
import { api, type Stats, type SystemStatus } from "@/lib/api";

const DnaHelix = dynamic(() => import("@/components/DnaHelix"), { ssr: false });

const PIPELINE = [
  { label: "VCF", icon: FileText, desc: "Raw variant calls" },
  { label: "Annotation", icon: Dna, desc: "Consequence, AF, scores" },
  { label: "ESM-2 + XGBoost", icon: BrainCircuit, desc: "AI pathogenicity" },
  { label: "ACMG Engine", icon: Scale, desc: "Deterministic evidence" },
  { label: "Reconciliation", icon: GitMerge, desc: "AI vs ACMG concordance" },
  { label: "Patient Context", icon: UserRound, desc: "Phenotype & meds" },
  { label: "Knowledge Graph", icon: Network, desc: "Evidence network" },
  { label: "Decision Support", icon: Stethoscope, desc: "Guideline-grounded" },
  { label: "Provenance", icon: Link2, desc: "Hash-chained ledger" },
];

function CountUp({ value }: { value: number }) {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (value === 0) return;
    const start = performance.now();
    const dur = 1200;
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / dur);
      setN(Math.round(value * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <span>{n.toLocaleString()}</span>;
}

export default function Overview() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    Promise.all([api.stats(), api.status()])
      .then(([s, st]) => {
        setStats(s);
        setStatus(st);
      })
      .catch(() => setOffline(true));
  }, []);

  const statCards = [
    { label: "Patients", value: stats?.patients ?? 0, icon: Users, accent: "text-cyan" },
    { label: "Variants analyzed", value: stats?.variants_analyzed ?? 0, icon: Dna, accent: "text-violet" },
    { label: "High-priority variants", value: stats?.high_priority_variants ?? 0, icon: AlertTriangle, accent: "text-warning" },
    { label: "Verified interpretations", value: stats?.verified_interpretations ?? 0, icon: BadgeCheck, accent: "text-success" },
  ];

  return (
    <div className="relative min-h-screen overflow-hidden">
      {/* Hero background */}
      <div className="absolute inset-0 grid-texture" />
      <div className="absolute -right-24 top-0 h-[620px] w-[620px] opacity-70">
        <DnaHelix className="h-full w-full" />
      </div>
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_30%_20%,rgba(0,229,255,0.07),transparent_70%)]" />

      <div className="relative z-10 mx-auto max-w-6xl px-8 py-14">
        {/* Hero */}
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: "easeOut" }}
        >
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-cyan/25 bg-cyan/5 px-4 py-1.5 text-xs tracking-widest text-cyan">
            <span className="size-1.5 rounded-full bg-cyan pulse-glow" />
            CLINICAL GENOMICS INTELLIGENCE · {status?.mode ?? "DEMO"}
          </div>
          <h1 className="text-6xl font-black tracking-tight">
            GENO<span className="text-gradient">GUIDE</span>
          </h1>
          <p className="mt-4 max-w-xl text-lg text-muted">
            AI-Powered Genomic Variant Interpretation &amp; Precision Decision Support
          </p>
          <p className="mt-2 max-w-xl text-sm text-muted/80">
            ESM-2 protein language representations and XGBoost run beside an independent,
            deterministic ACMG/AMP rule engine — reconciled, contextualized to the patient,
            and sealed on a hash-chained provenance ledger.
          </p>

          <div className="mt-8 flex items-center gap-4">
            <Link
              href="/variant-lab"
              className="group inline-flex items-center gap-2 rounded-xl border border-cyan/40 bg-cyan/10 px-6 py-3 text-sm font-semibold text-cyan transition-all hover:bg-cyan/20 hover:shadow-[0_0_32px_-8px_#00e5ff]"
            >
              <FlaskConical className="size-4" />
              Open Variant Lab
              <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
            </Link>
            <Link
              href="/patient-context"
              className="inline-flex items-center gap-2 rounded-xl border border-white/10 px-6 py-3 text-sm text-muted transition-colors hover:border-violet/40 hover:text-violet"
            >
              <UserRound className="size-4" />
              Patient G-1027 showcase
            </Link>
          </div>

          {offline && (
            <p className="mt-4 text-sm text-warning">
              Backend not reachable — start it with{" "}
              <code className="mono rounded bg-white/5 px-1.5 py-0.5">uvicorn app.main:app --port 8000</code>
            </p>
          )}
        </motion.div>

        {/* Stats */}
        <div className="mt-14 grid grid-cols-2 gap-4 lg:grid-cols-4">
          {statCards.map((s, i) => (
            <motion.div
              key={s.label}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 + i * 0.08, duration: 0.5 }}
              className="card p-5"
            >
              <div className="flex items-center justify-between">
                <s.icon className={`size-4 ${s.accent}`} />
                <span className="text-[10px] uppercase tracking-widest text-muted">{s.label}</span>
              </div>
              <p className="mt-3 text-3xl font-bold tabular-nums">
                <CountUp value={s.value} />
              </p>
            </motion.div>
          ))}
        </div>

        {/* Pipeline */}
        <motion.section
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5, duration: 0.6 }}
          className="mt-14"
        >
          <h2 className="mb-1 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
            System pipeline
          </h2>
          <p className="mb-5 text-sm text-muted/70">
            From raw VCF to a verifiable, guideline-grounded interpretation.
          </p>
          <div className="card card-glow-cyan flex flex-wrap items-stretch gap-y-4 p-5">
            {PIPELINE.map((stage, i) => (
              <div key={stage.label} className="flex items-center">
                <motion.div
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: 0.6 + i * 0.08 }}
                  className="flex w-[104px] flex-col items-center gap-2 text-center"
                >
                  <span className="grid size-11 place-items-center rounded-xl border border-white/10 bg-panel2 transition-colors hover:border-cyan/40">
                    <stage.icon className="size-5 text-cyan" />
                  </span>
                  <span className="text-[11px] font-semibold leading-tight">{stage.label}</span>
                  <span className="text-[9px] leading-tight text-muted">{stage.desc}</span>
                </motion.div>
                {i < PIPELINE.length - 1 && (
                  <ArrowRight className="mx-0.5 size-3.5 shrink-0 text-cyan/40" />
                )}
              </div>
            ))}
          </div>
        </motion.section>

        {/* Component status + governance principles */}
        <div className="mt-10 grid gap-4 lg:grid-cols-2">
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.7 }}
            className="card p-5"
          >
            <h3 className="mb-4 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
              Engine readiness
            </h3>
            <div className="grid grid-cols-2 gap-3">
              {(status?.components ?? []).map((c) => (
                <div
                  key={c.name}
                  className="flex items-center justify-between rounded-lg border border-success/25 bg-success/5 px-4 py-3"
                >
                  <span className="text-sm font-medium">{c.name}</span>
                  <span className="flex items-center gap-1.5 text-xs font-semibold text-success">
                    <CheckCircle2 className="size-3.5" /> READY
                  </span>
                </div>
              ))}
            </div>
            {status && (
              <p className="mono mt-4 text-[10px] text-muted">
                {status.model_version} · {status.evidence_version}
              </p>
            )}
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.8 }}
            className="card card-glow-violet p-5"
          >
            <h3 className="mb-4 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
              Governance by design
            </h3>
            <ul className="space-y-3 text-sm text-muted">
              <li className="flex gap-3">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-violet" />
                ML never overrides ACMG evidence — discordance triggers mandatory human review.
              </li>
              <li className="flex gap-3">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-violet" />
                No genomic data on-chain: only hashes, consent state, versions and timestamps.
              </li>
              <li className="flex gap-3">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-violet" />
                Every interpretation is reproducible: model + evidence versions sealed per record.
              </li>
              <li className="flex gap-3">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-violet" />
                Patient records shown here are synthetic demo data — clearly labeled throughout.
              </li>
            </ul>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
