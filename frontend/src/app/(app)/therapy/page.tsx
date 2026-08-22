"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FlaskConical,
  Loader2,
  Pill,
  ShieldAlert,
  Sparkles,
  WifiOff,
} from "lucide-react";
import {
  api,
  type SomaticTherapy,
  type TherapyStatus,
} from "@/lib/api";
import { mapProteinChange } from "@/lib/protein";

const PRESETS = [
  { label: "EGFR L858R · NSCLC", gene: "EGFR", variant: "L858R", disease: "NSCLC", hgvs: "p.Leu858Arg" },
  { label: "BRAF V600E · Melanoma", gene: "BRAF", variant: "V600E", disease: "Melanoma", hgvs: "p.Val600Glu" },
  { label: "KRAS G12C · NSCLC", gene: "KRAS", variant: "G12C", disease: "NSCLC", hgvs: "p.Gly12Cys" },
  { label: "EGFR T790M · NSCLC", gene: "EGFR", variant: "T790M", disease: "NSCLC", hgvs: "p.Thr790Met" },
];

function evidenceTone(level: string): string {
  if (level === "A") return "border-success/40 bg-success/10 text-success";
  if (level === "B") return "border-cyan/40 bg-cyan/10 text-cyan";
  if (level === "C") return "border-warning/40 bg-warning/10 text-warning";
  return "border-navy-950/15 bg-navy-950/5 text-muted";
}

function responseTone(response: string): string {
  const r = response.toLowerCase();
  if (r.includes("sensit")) return "text-success";
  if (r.includes("resist")) return "text-error";
  return "text-muted";
}

export default function TherapyPage() {
  const [status, setStatus] = useState<TherapyStatus | null>(null);
  const [gene, setGene] = useState("EGFR");
  const [variant, setVariant] = useState("L858R");
  const [disease, setDisease] = useState("NSCLC");
  const [hgvs, setHgvs] = useState("p.Leu858Arg");
  const [mapped, setMapped] = useState<string | null>("L858R");
  const [result, setResult] = useState<SomaticTherapy | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.therapyStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    const local = mapProteinChange(hgvs) ?? mapProteinChange(variant);
    setMapped(local);
    if (!hgvs.trim()) return;
    api.therapyMap(hgvs.trim(), disease)
      .then((m) => {
        if (m.protein_shorthand) setMapped(m.protein_shorthand);
      })
      .catch(() => undefined);
  }, [hgvs, disease, variant]);

  const offline = !status;
  const enabled = Boolean(status?.enabled);

  async function run(next?: { gene: string; variant: string; disease: string }) {
    const g = next?.gene ?? gene;
    const v = next?.variant ?? variant;
    const d = next?.disease ?? disease;
    setGene(g);
    setVariant(v);
    setDisease(d);
    setBusy(true);
    setError(null);
    try {
      const rec = await api.therapyRecommend(g, mapProteinChange(v) ?? v, d);
      setResult(rec);
    } catch (e) {
      setError(e instanceof Error ? e.message : "request failed");
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  const recs = result?.recommendations ?? [];
  const maxScore = recs[0]?.score ?? 1;

  const availabilityNote = useMemo(() => {
    if (!result) return null;
    switch (result.availability) {
      case "AVAILABLE":
        return { tone: "text-success", text: "Ranking attached — specialist review required" };
      case "SOURCE_NOT_CONFIGURED":
        return {
          tone: "text-warning",
          text: "In-repo ranker unavailable. Restart the FastAPI process from the repo root so Medical_DrugRecommendation can load.",
        };
      case "SOURCE_UNAVAILABLE":
        return { tone: "text-error", text: result.reason ?? "Remote engine unavailable" };
      case "SKIPPED":
        return { tone: "text-warning", text: result.reason ?? "Query skipped" };
      default:
        return { tone: "text-muted", text: result.reason ?? result.availability };
    }
  }, [result]);

  return (
    <div className="mx-auto max-w-7xl px-8 py-10">
      <header className="mb-6">
        <h1 className="flex items-center gap-3 text-2xl font-bold tracking-tight">
          <Pill className="size-6 text-cyan" />
          Oncology therapy ranking
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          External somatic ranker (CIViC / DGIdb / ML hybrid). This panel does not replace
          ACMG classification, Variant Lab, or Patient Context PGx. Rankings are not
          prescriptions.
        </p>
      </header>

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <span className={`rounded-lg border px-3 py-1.5 text-[11px] uppercase tracking-widest ${
          enabled ? "border-success/40 bg-success/10 text-success" : "border-warning/40 bg-warning/10 text-warning"
        }`}>
          {offline ? "backend unreachable" : enabled ? "connector enabled" : "connector offline"}
        </span>
        <span className="text-[11px] text-muted">
          Distinct from CPIC pharmacogenomics (CYP2D6 / Tamoxifen).
        </span>
      </div>

      <div className="mb-6 rounded-xl border border-warning/30 bg-warning/5 p-4 text-sm text-warning">
        <p className="flex items-start gap-2">
          <ShieldAlert className="mt-0.5 size-4 shrink-0" />
          <span>
            Research / decision-support only. Do not start, stop, or substitute a drug from this
            list. Review applicable oncology guidelines with a qualified specialist. ACMG/AMP
            classification is unchanged by these scores.
          </span>
        </p>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            onClick={() => {
              setHgvs(p.hgvs);
              void run(p);
            }}
            className={`rounded-xl border px-3 py-2 text-left text-sm transition-all ${
              gene === p.gene && variant === p.variant
                ? "border-cyan/50 bg-cyan/10 shadow-[0_0_18px_-8px_#b4182d]"
                : "border-navy-950/10 bg-panel2/60 hover:border-navy-950/25"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="mb-8 grid gap-4 lg:grid-cols-[1fr_1.4fr]">
        <div className="card card-glow-cyan p-5">
          <p className="mb-3 text-[10px] font-semibold uppercase tracking-widest text-muted">
            Query (protein change, not genomic ID)
          </p>
          <label className="mb-3 block text-xs text-muted">
            Gene
            <input
              value={gene}
              onChange={(e) => setGene(e.target.value.toUpperCase())}
              className="mt-1 w-full rounded-lg border border-navy-950/10 bg-bg px-3 py-2 font-mono text-sm text-fg"
            />
          </label>
          <label className="mb-3 block text-xs text-muted">
            Protein variant
            <input
              value={variant}
              onChange={(e) => setVariant(e.target.value)}
              className="mt-1 w-full rounded-lg border border-navy-950/10 bg-bg px-3 py-2 font-mono text-sm text-fg"
              placeholder="L858R"
            />
          </label>
          <label className="mb-3 block text-xs text-muted">
            HGVS.p mapper
            <input
              value={hgvs}
              onChange={(e) => {
                setHgvs(e.target.value);
                const next = e.target.value;
                const mappedLocal = mapProteinChange(next);
                if (mappedLocal) setVariant(mappedLocal);
                void api.therapyMap(next).then((m) => {
                  if (m.protein_shorthand) setVariant(m.protein_shorthand);
                }).catch(() => undefined);
              }}
              className="mt-1 w-full rounded-lg border border-navy-950/10 bg-bg px-3 py-2 font-mono text-sm text-fg"
              placeholder="p.Leu858Arg"
            />
          </label>
          <p className="mb-3 font-mono text-xs text-cyan">
            mapped: {mapped ?? "unmappable — will not guess from c. / genomic coordinates"}
          </p>
          <label className="mb-4 block text-xs text-muted">
            Oncology indication
            <input
              value={disease}
              onChange={(e) => setDisease(e.target.value)}
              className="mt-1 w-full rounded-lg border border-navy-950/10 bg-bg px-3 py-2 text-sm text-fg"
              placeholder="NSCLC"
            />
          </label>
          <button
            onClick={() => void run()}
            disabled={busy}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-cyan/40 bg-cyan/15 py-2.5 text-sm font-semibold text-cyan disabled:opacity-50"
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
            Rank therapies
          </button>
          {error && <p className="mt-3 text-xs text-error">{error}</p>}
        </div>

        <div className="card p-5">
          <p className="mb-3 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-muted">
            <FlaskConical className="size-3.5" /> Result
          </p>
          {!result && !busy && (
            <p className="flex items-center gap-2 text-sm text-muted">
              {offline ? <WifiOff className="size-4" /> : <ArrowRight className="size-4" />}
              {offline
                ? "Start the FastAPI server, then rank a preset."
                : "Pick a preset or submit a protein change."}
            </p>
          )}
          {availabilityNote && (
            <p className={`mb-4 text-sm ${availabilityNote.tone}`}>{availabilityNote.text}</p>
          )}
          {recs.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-[10px] uppercase tracking-widest text-muted">
                  <tr>
                    <th className="pb-2">Rank</th>
                    <th className="pb-2">Agent</th>
                    <th className="pb-2">Score</th>
                    <th className="pb-2">Response</th>
                    <th className="pb-2">Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {recs.map((r) => (
                    <motion.tr
                      key={`${r.rank}-${r.drug}`}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="border-t border-navy-950/8"
                    >
                      <td className="py-2.5 font-mono text-muted">{r.rank}</td>
                      <td className="py-2.5 font-medium">{r.drug}</td>
                      <td className="py-2.5">
                        <div className="flex items-center gap-2">
                          <span className="w-12 font-mono text-xs">{r.score.toFixed(3)}</span>
                          <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-navy-950/10">
                            <span
                              className="block h-full rounded-full bg-cyan"
                              style={{ width: `${Math.max(8, (r.score / maxScore) * 100)}%` }}
                            />
                          </span>
                        </div>
                      </td>
                      <td className={`py-2.5 text-xs ${responseTone(r.response)}`}>{r.response}</td>
                      <td className="py-2.5">
                        <span className={`rounded border px-2 py-0.5 text-[10px] ${evidenceTone(r.evidence_level)}`}>
                          {r.evidence_level} · n={r.evidence_count}
                        </span>
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {result?.availability === "AVAILABLE" && (
            <p className="mt-4 flex items-center gap-2 text-[11px] text-muted">
              <CheckCircle2 className="size-3.5 text-success" />
              Human review required · {result.latency_ms ?? "—"} ms
              {result.cached ? " · cached" : ""} · hashes stored on the payload, not as ACMG evidence
            </p>
          )}
        </div>
      </div>

      <p className="flex items-start gap-2 text-xs text-muted">
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" />
        Ngrok-free hosts change every session. If this page shows SOURCE_NOT_CONFIGURED, the rest of
        GenoGuide (ACMG, Variant Lab, provenance) is still fully usable offline.
      </p>
    </div>
  );
}
