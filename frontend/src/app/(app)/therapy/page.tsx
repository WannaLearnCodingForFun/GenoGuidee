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
  const [gene, setGene] = useState("");
  const [variant, setVariant] = useState("");
  const [disease, setDisease] = useState("");
  const [hgvs, setHgvs] = useState("");
  const [mapped, setMapped] = useState<string | null>(null);
  const [result, setResult] = useState<SomaticTherapy | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backendDown, setBackendDown] = useState(false);

  useEffect(() => {
    api.therapyStatus()
      .then((s) => {
        setStatus(s);
        setBackendDown(false);
      })
      .catch(() => {
        setStatus(null);
        setBackendDown(true);
      });
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

  const enabled = Boolean(status?.enabled || status?.local_engine);

  function applyPreset(p: (typeof PRESETS)[number]) {
    setGene(p.gene);
    setVariant(p.variant);
    setDisease(p.disease);
    setHgvs(p.hgvs);
    setMapped(p.variant);
    setResult(null);
    setError(null);
  }

  async function run() {
    const g = gene.trim().toUpperCase();
    const protein = mapProteinChange(variant) ?? mapProteinChange(hgvs) ?? variant.trim();
    const d = disease.trim();
    if (!g || !protein || !d) {
      setError("Gene, protein variant, and oncology indication are required.");
      return;
    }
    if (!mapProteinChange(variant) && !mapProteinChange(hgvs) && !/^[A-Z*]\d+[A-Z*]$/.test(protein)) {
      setError("Unable to safely normalize this variant. Please provide a supported protein HGVS expression.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const rec = await api.frontendTherapy({
        mutation: { gene: g, protein_change: protein, hgvs_p: hgvs || undefined },
        clinical: { indication: d },
      });
      setResult(rec.recommendation);
      setBackendDown(false);
    } catch (e) {
      const message = e instanceof Error ? e.message : "request failed";
      setError(message);
      setResult(null);
      if (message.includes("BACKEND UNAVAILABLE")) setBackendDown(true);
    } finally {
      setBusy(false);
    }
  }

  const recs = result?.recommendations ?? [];
  const maxScore = recs[0]?.score ?? 1;
  const abstained = Boolean(result?.abstained) || (result != null && recs.length === 0 && result.availability !== "AVAILABLE");

  const availabilityNote = useMemo(() => {
    if (!result) return null;
    if (result.abstained) {
      return { tone: "text-warning", text: "No validated therapy ranking for this combination." };
    }
    switch (result.availability) {
      case "AVAILABLE":
        return { tone: "text-success", text: "Ranking attached — specialist review required" };
      case "SOURCE_NOT_CONFIGURED":
        return {
          tone: "text-warning",
          text: "Therapy ranker is not configured. Restart with GENOGUIDE_DRUG_LOCAL=true, or set a remote engine URL.",
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
          Therapy ranking
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          Enter your genomic alteration. This is downstream research / decision-support
          only — not a prescription, not ACMG, and not CPIC pharmacogenomics.
        </p>
      </header>

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <span className={`rounded-lg border px-3 py-1.5 text-[11px] uppercase tracking-widest ${
          backendDown
            ? "border-error/40 bg-error/10 text-error"
            : enabled
              ? "border-success/40 bg-success/10 text-success"
              : "border-warning/40 bg-warning/10 text-warning"
        }`}>
          {backendDown ? "backend offline" : enabled ? "local ranker ready" : "ranker not configured"}
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

      <div className="mb-8 grid gap-4 lg:grid-cols-[1fr_1.4fr]">
        <div className="card card-glow-cyan p-5">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-cyan">
            Enter your own variant
          </p>
          <p className="mb-3 text-[10px] font-semibold uppercase tracking-widest text-muted">
            Gene · protein change · indication
          </p>
          <label className="mb-3 block text-xs text-muted">
            Gene
            <input
              value={gene}
              onChange={(e) => setGene(e.target.value.toUpperCase())}
              className="mt-1 w-full rounded-lg border border-navy-950/10 bg-bg px-3 py-2 font-mono text-sm text-fg"
              placeholder="EGFR"
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
            HGVS protein
            <input
              value={hgvs}
              onChange={(e) => {
                setHgvs(e.target.value);
                const mappedLocal = mapProteinChange(e.target.value);
                if (mappedLocal) setVariant(mappedLocal);
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

          <p className="mb-2 mt-6 text-[10px] font-semibold uppercase tracking-widest text-muted">
            Quick demo cases
          </p>
          <div className="flex flex-wrap gap-2">
            {PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                onClick={() => applyPreset(p)}
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
        </div>

        <div className="card p-5">
          <p className="mb-3 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-muted">
            <FlaskConical className="size-3.5" /> Result
          </p>
          {!result && !busy && (
            <p className="flex items-center gap-2 text-sm text-muted">
              {backendDown ? <WifiOff className="size-4" /> : <ArrowRight className="size-4" />}
              {backendDown
                ? "BACKEND UNAVAILABLE — start the FastAPI server on port 8000."
                : "Enter a gene, protein variant, and indication, then rank."}
            </p>
          )}
          {abstained && result && (
            <div className="mb-4 rounded-xl border border-warning/30 bg-warning/5 p-4">
              <p className="text-sm font-semibold text-warning">No validated therapy ranking</p>
              <p className="mt-1 text-sm text-muted">
                This variant/indication combination is outside the currently validated
                evidence/model coverage.
              </p>
              {result.reason && <p className="mt-2 font-mono text-xs text-muted">{result.reason}</p>}
            </div>
          )}
          {availabilityNote && !abstained && (
            <p className={`mb-4 text-sm ${availabilityNote.tone}`}>{availabilityNote.text}</p>
          )}
          {recs.length > 0 && (
            <div className="space-y-3">
              {recs.map((r) => (
                <motion.article
                  key={`${r.rank}-${r.drug}`}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="rounded-xl border border-navy-950/8 p-4"
                >
                  <p className="text-[10px] uppercase tracking-widest text-muted">Rank #{r.rank}</p>
                  <h3 className="mt-1 text-base font-semibold">{r.drug}</h3>
                  <dl className="mt-3 grid gap-2 text-xs">
                    <div className="flex justify-between gap-4">
                      <dt className="text-muted">Evidence</dt>
                      <dd className={`rounded border px-2 py-0.5 ${evidenceTone(r.evidence_level)}`}>
                        {r.evidence_level || "Evidence unavailable"} · n={r.evidence_count}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-4">
                      <dt className="text-muted">Variant association</dt>
                      <dd className={responseTone(r.response)}>{r.response || "Evidence unavailable"}</dd>
                    </div>
                    <div className="flex justify-between gap-4">
                      <dt className="text-muted">Indication match</dt>
                      <dd>{result?.request?.disease || "Evidence unavailable"}</dd>
                    </div>
                    <div className="flex justify-between gap-4">
                      <dt className="text-muted">Why ranked</dt>
                      <dd className="text-right">{result?.reason || "Score from the in-repo evidence/ML ranker"}</dd>
                    </div>
                    <div className="flex justify-between gap-4">
                      <dt className="text-muted">Source</dt>
                      <dd className="font-mono">{result?.endpoint || "Evidence unavailable"}</dd>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                      <dt className="text-muted">Score</dt>
                      <dd className="flex w-40 items-center gap-2">
                        <span className="font-mono">{r.score.toFixed(3)}</span>
                        <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-navy-950/10">
                          <span
                            className="block h-full rounded-full bg-cyan"
                            style={{ width: `${Math.max(8, (r.score / maxScore) * 100)}%` }}
                          />
                        </span>
                      </dd>
                    </div>
                  </dl>
                </motion.article>
              ))}
            </div>
          )}
          {result?.availability === "AVAILABLE" && recs.length > 0 && (
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
        Ngrok is optional. If the remote tunnel is offline, local ACMG, research, and
        in-repo therapy ranking still work on localhost.
      </p>
    </div>
  );
}
