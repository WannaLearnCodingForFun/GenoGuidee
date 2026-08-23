"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { motion } from "framer-motion";
import {
  ArrowRight,
  BadgeCheck,
  BrainCircuit,
  ChevronDown,
  Dna,
  FileText,
  FlaskConical,
  GitMerge,
  Link2,
  Lock,
  Network,
  Scale,
  ShieldCheck,
  Stethoscope,
  UserRound,
  Users,
} from "lucide-react";
import { api, type Stats } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";

const DnaHelix = dynamic(() => import("@/components/DnaHelix"), { ssr: false });

const PIPELINE = [
  { label: "VCF", icon: FileText, desc: "Raw variant calls" },
  { label: "Annotation", icon: Dna, desc: "Consequence, AF, scores" },
  { label: "ESM-2 + XGBoost", icon: BrainCircuit, desc: "AI pathogenicity" },
  { label: "ACMG Engine", icon: Scale, desc: "Deterministic evidence" },
  { label: "Reconciliation", icon: GitMerge, desc: "AI vs ACMG concordance" },
  { label: "Patient Context", icon: UserRound, desc: "Phenotype & meds" },
  { label: "Knowledge Graph", icon: Network, desc: "Evidence network" },
  { label: "Provenance", icon: Link2, desc: "Hash-chained ledger" },
];

const FEATURES = [
  {
    icon: BrainCircuit,
    accent: "crimson",
    title: "Dual-engine interpretation",
    desc: "ESM-2 protein language representations feed an XGBoost classifier that runs beside an independent, deterministic ACMG/AMP rule engine — never in place of it.",
  },
  {
    icon: GitMerge,
    accent: "maroon",
    title: "Reconciliation, not override",
    desc: "AI and rule-based verdicts are compared automatically. Discordance is surfaced, flagged, and routed to mandatory human review — the model never has the final word.",
  },
  {
    icon: UserRound,
    accent: "crimson",
    title: "Patient-contextualized",
    desc: "Every variant is scored against phenotype, medication, and family history — not interpreted in a vacuum.",
  },
  {
    icon: Network,
    accent: "maroon",
    title: "Evidence knowledge graph",
    desc: "Genes, variants, conditions, and guideline citations are traversable as a graph, so every call is explainable end to end.",
  },
  {
    icon: Link2,
    accent: "crimson",
    title: "Hash-chained provenance",
    desc: "Every interpretation is sealed to a tamper-evident, hash-chained ledger with model and evidence versions — reproducible on demand.",
  },
  {
    icon: ShieldCheck,
    accent: "maroon",
    title: "Governance by design",
    desc: "No raw genomic data ever touches the ledger — only hashes, consent state, and versioned timestamps.",
  },
];

const FAQ = [
  {
    q: "Does the AI model override ACMG classifications?",
    a: "No. The ESM-2/XGBoost model and the deterministic ACMG/AMP rule engine run independently. Their outputs are reconciled — any discordance is flagged for mandatory human review rather than silently resolved in the model's favor.",
  },
  {
    q: "What data does the provenance ledger actually store?",
    a: "Only hashes, consent state, model/evidence versions, and timestamps — never raw genomic sequence or PHI. Every recorded interpretation is independently verifiable against its hash chain.",
  },
  {
    q: "Is this connected to real patient data?",
    a: "The instance you can launch from this page runs entirely on synthetic, clearly-labeled demo patients and variants — no real genomic or clinical data is used.",
  },
  {
    q: "What guidance framework does the rule engine implement?",
    a: "A deterministic evidence engine modeled on ACMG/AMP variant classification criteria, with each met criterion traceable to its source evidence.",
  },
];

function useCountUp(value: number) {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!value) return;
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
  return n;
}

function CountUp({ value }: { value: number }) {
  return <span>{useCountUp(value).toLocaleString()}</span>;
}

function FaqItem({ q, a, defaultOpen }: { q: string; a: string; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(!!defaultOpen);
  return (
    <div className="mkt-card overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left"
      >
        <span className="text-sm font-semibold text-navy-950">{q}</span>
        <ChevronDown
          className={`size-4 shrink-0 text-navy-800 transition-transform ${open ? "rotate-180 text-crimson" : ""}`}
        />
      </button>
      <motion.div
        initial={false}
        animate={{ height: open ? "auto" : 0, opacity: open ? 1 : 0 }}
        transition={{ duration: 0.25, ease: "easeInOut" }}
        className="overflow-hidden"
      >
        <p className="px-5 pb-4 text-sm text-navy-800">{a}</p>
      </motion.div>
    </div>
  );
}

export default function Landing() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [accountStats, setAccountStats] = useState<{ patients: number; doctors: number } | null>(
    null,
  );

  useEffect(() => {
    api.stats().then(setStats).catch(() => setStats(null));
  }, []);

  useEffect(() => {
    const supabase = createClient();
    supabase
      .rpc("landing_stats")
      .single()
      .then(({ data, error }: { data: { patients: number; doctors: number } | null; error: { message?: string } | null }) => {
        if (error || !data) return;
        const row = data as { patients: number; doctors: number };
        setAccountStats({ patients: row.patients, doctors: row.doctors });
      });
  }, []);

  const statCards = [
    { label: "Registered patients", value: accountStats?.patients ?? 0, icon: Users },
    { label: "Registered doctors", value: accountStats?.doctors ?? 0, icon: Stethoscope },
    { label: "Variants analyzed", value: stats?.variants_analyzed ?? 0, icon: Dna },
    { label: "Verified interpretations", value: stats?.verified_interpretations ?? 0, icon: BadgeCheck },
  ];

  return (
    <div className="relative overflow-hidden bg-white">
      {/* ---------------------------------------------------------------- Hero */}
      <section className="relative">
        <div className="mkt-grid-texture absolute inset-0" />
        <div className="absolute -right-24 top-0 h-[620px] w-[620px] opacity-60">
          <DnaHelix className="h-full w-full" strandA="#b4182d" strandB="#37415c" rung="#242e49" />
        </div>
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_30%_20%,rgba(180,24,45,0.05),transparent_70%)]" />

        <div className="relative z-10 mx-auto max-w-6xl px-6 pb-20 pt-20 lg:px-8 lg:pt-28">
          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: "easeOut" }}
          >
            <h1 className="max-w-3xl text-5xl font-black leading-[1.05] tracking-tight text-navy-950 lg:text-6xl">
              Variant interpretation that is <span className="mkt-text-gradient">explainable, reconciled,</span> and provable.
            </h1>

            <div className="mt-9 flex flex-wrap items-center gap-4">
              <Link
                href="/dashboard"
                className="group inline-flex items-center gap-2 rounded-xl bg-crimson px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-maroon"
              >
                <FlaskConical className="size-4" />
                Launch the platform
                <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
              </Link>
            </div>
          </motion.div>

          {/* Live stats */}
          <div className="mt-24 grid grid-cols-2 gap-4 lg:grid-cols-4">
            {statCards.map((s, i) => (
              <motion.div
                key={s.label}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15 + i * 0.08, duration: 0.5 }}
                className="mkt-card p-5"
              >
                <div className="flex items-center justify-between">
                  <s.icon className="size-4 text-crimson" />
                  <span className="text-[10px] uppercase tracking-widest text-navy-800">{s.label}</span>
                </div>
                <p className="mt-3 text-3xl font-bold tabular-nums text-navy-950">
                  <CountUp value={s.value} />
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------- Features */}
      <section id="product" className="mx-auto max-w-6xl px-6 py-20 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5 }}
        >
          <h2 className="text-xs font-semibold uppercase tracking-[0.25em] text-crimson">Product</h2>
          <p className="mt-2 max-w-xl text-3xl font-bold tracking-tight text-navy-950">
            Built for the moment a wrong call has clinical consequences.
          </p>
        </motion.div>

        <div className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ delay: (i % 3) * 0.08, duration: 0.45 }}
              className="mkt-card mkt-card-hoverable p-6 transition-all hover:-translate-y-1"
            >
              <span
                className={`grid size-10 place-items-center rounded-xl border ${
                  f.accent === "crimson"
                    ? "border-crimson/25 bg-crimson/10 text-crimson"
                    : "border-maroon/25 bg-maroon/6 text-maroon"
                }`}
              >
                <f.icon className="size-5" />
              </span>
              <h3 className="mt-4 text-base font-semibold text-navy-950">{f.title}</h3>
              <p className="mt-2 text-sm text-navy-800">{f.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ---------------------------------------------------------------- How it works */}
      <section id="how-it-works" className="mx-auto max-w-6xl px-6 py-20 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5 }}
        >
          <h2 className="text-xs font-semibold uppercase tracking-[0.25em] text-crimson">How it works</h2>
          <p className="mt-2 max-w-xl text-3xl font-bold tracking-tight text-navy-950">
            From raw VCF to a verifiable, guideline-grounded interpretation.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.6 }}
          className="mkt-card mkt-card-glow mt-8 flex flex-wrap items-stretch gap-y-4 p-6"
        >
          {PIPELINE.map((stage, i) => (
            <div key={stage.label} className="flex items-center">
              <div className="flex w-[108px] flex-col items-center gap-2 text-center">
                <span className="grid size-11 place-items-center rounded-xl border border-navy-800/15 bg-navy-950/[0.03] transition-colors hover:border-crimson/40">
                  <stage.icon className="size-5 text-crimson" />
                </span>
                <span className="text-[11px] font-semibold leading-tight text-navy-950">{stage.label}</span>
                <span className="text-[9px] leading-tight text-navy-800">{stage.desc}</span>
              </div>
              {i < PIPELINE.length - 1 && (
                <ArrowRight className="mx-0.5 size-3.5 shrink-0 text-crimson/35" />
              )}
            </div>
          ))}
        </motion.div>
      </section>

      {/* ---------------------------------------------------------------- Security / governance */}
      <section id="security" className="mx-auto max-w-6xl px-6 py-20 lg:px-8">
        <div className="grid gap-10 lg:grid-cols-2 lg:items-center">
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.5 }}
          >
            <h2 className="text-xs font-semibold uppercase tracking-[0.25em] text-crimson">Security &amp; governance</h2>
            <p className="mt-2 text-3xl font-bold tracking-tight text-navy-950">
              The model informs the decision. It never makes it alone.
            </p>
            <p className="mt-4 max-w-md text-sm text-navy-800">
              Every design choice in GenoGuide traces back to one principle: a clinician must be
              able to reconstruct, verify, and trust exactly why a variant was classified the way
              it was.
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ delay: 0.1, duration: 0.5 }}
            className="mkt-card mkt-card-glow p-6"
          >
            <ul className="space-y-4 text-sm text-navy-800">
              <li className="flex gap-3">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-crimson" />
                ML never overrides ACMG evidence — discordance triggers mandatory human review.
              </li>
              <li className="flex gap-3">
                <Lock className="mt-0.5 size-4 shrink-0 text-crimson" />
                No genomic data on-chain: only hashes, consent state, versions and timestamps.
              </li>
              <li className="flex gap-3">
                <BadgeCheck className="mt-0.5 size-4 shrink-0 text-crimson" />
                Every interpretation is reproducible: model + evidence versions sealed per record.
              </li>
              <li className="flex gap-3">
                <Stethoscope className="mt-0.5 size-4 shrink-0 text-crimson" />
                Patient records in this demo are synthetic — clearly labeled throughout the app.
              </li>
            </ul>
          </motion.div>
        </div>
      </section>

      {/* ---------------------------------------------------------------- FAQ */}
      <section id="faq" className="mx-auto max-w-3xl px-6 py-20 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5 }}
        >
          <h2 className="text-xs font-semibold uppercase tracking-[0.25em] text-crimson">FAQ</h2>
          <p className="mt-2 text-3xl font-bold tracking-tight text-navy-950">Common questions</p>
        </motion.div>
        <div className="mt-8 space-y-3">
          {FAQ.map((item, i) => (
            <FaqItem key={item.q} q={item.q} a={item.a} defaultOpen={i === 0} />
          ))}
        </div>
      </section>

      {/* ---------------------------------------------------------------- CTA */}
      <section className="mx-auto max-w-6xl px-6 pb-24 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5 }}
          className="relative overflow-hidden rounded-2xl bg-navy-950 p-10 text-center lg:p-14"
        >
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_60%_at_50%_0%,rgba(253,164,129,0.12),transparent_70%)]" />
          <h2 className="relative text-3xl font-bold tracking-tight text-white lg:text-4xl">
            See a variant go from raw call to verified interpretation.
          </h2>
          <p className="relative mx-auto mt-3 max-w-xl text-sm text-white/65">
            Open the live demo instance — run a real analysis end to end, from ESM-2 scoring through
            ACMG reconciliation to the provenance ledger.
          </p>
          <div className="relative mt-8 flex justify-center">
            <Link
              href="/dashboard"
              className="group inline-flex items-center gap-2 rounded-xl bg-crimson px-7 py-3.5 text-sm font-semibold text-white transition-colors hover:bg-maroon"
            >
              <FlaskConical className="size-4" />
              Launch the platform
              <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
            </Link>
          </div>
        </motion.div>
      </section>
    </div>
  );
}
