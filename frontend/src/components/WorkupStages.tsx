"use client";

import {
  AlertTriangle,
  BrainCircuit,
  CheckCircle2,
  ClipboardList,
  Dna,
  FlaskConical,
  GitMerge,
  Info,
  Pill,
  Scale,
  ShieldCheck,
  Stethoscope,
} from "lucide-react";
import type { WorkupResult, WorkupSnapshot } from "@/lib/api";
import { classColor, formatAf } from "@/lib/ui";

export function workupPayload(snap: WorkupSnapshot | null | undefined): WorkupResult | null {
  if (!snap) return null;
  const direct = snap.payload;
  if (direct && typeof direct === "object" && !Array.isArray(direct) && direct.stages) {
    return direct;
  }
  const raw = (snap as WorkupSnapshot & { payload_json?: string }).payload_json;
  if (typeof raw === "string") {
    try {
      const parsed = JSON.parse(raw) as WorkupResult;
      if (parsed?.stages) return parsed;
    } catch {
      /* ignore malformed snapshot */
    }
  }
  return null;
}

export function WorkupStages({ result }: { result: WorkupResult }) {
  return (
    <div className="space-y-6">
      <TripleStage result={result} />
      <ClassificationStage result={result} />
      <ReconciliationStage result={result} />
      <MedicationStage result={result} />
      <ConsiderationsCard result={result} />
    </div>
  );
}

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

function ClassificationStage({ result }: { result: WorkupResult }) {
  const cc = classColor(result.acmg.classification);
  const probs = Object.entries(result.ml.probabilities ?? {}).sort((a, b) => b[1] - a[1]);
  const confidence = typeof result.ml.confidence === "number" ? result.ml.confidence : null;

  return (
    <section className="card p-6">
      <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
        <BrainCircuit className="size-3.5" /> Step 3 &middot; Classification
      </h2>
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="rounded-xl border border-violet/25 bg-violet/[0.04] p-4">
          <h3 className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.2em] text-violet">
            <BrainCircuit className="size-3.5" /> AI path — ESM-2 + XGBoost
          </h3>
          <p className="mt-3 text-xl font-bold">{result.ml.top_class}</p>
          <p className="text-xs text-muted">
            {confidence != null ? `confidence ${(confidence * 100).toFixed(1)}% · ` : ""}
            {result.ml.engine}
          </p>
          <div className="mt-3 space-y-1.5">
            {probs.map(([k, v]) => (
              <div key={k} className="flex items-center gap-2">
                <span className="w-32 shrink-0 text-[11px] capitalize text-muted">
                  {k.replace(/_/g, " ")}
                </span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-navy-950/10">
                  <div className="h-full rounded-full bg-violet" style={{ width: `${Number(v) * 100}%` }} />
                </div>
                <span className="mono w-12 shrink-0 text-right text-[10px] text-muted">
                  {(Number(v) * 100).toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11px] text-muted">
            ESM-2 delta {result.esm2?.delta_score ?? "—"} · {result.esm2?.mode ?? "—"}
          </p>
        </div>
        <div className="rounded-xl border border-cyan/25 bg-cyan/[0.04] p-4">
          <h3 className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.2em] text-cyan">
            <Scale className="size-3.5" /> ACMG path — deterministic rules
          </h3>
          <p className={`mt-3 text-xl font-bold ${cc.text}`}>{result.acmg.classification}</p>
          <p className="text-xs text-muted">{result.acmg.framework}</p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {result.acmg.met_criteria?.length ? (
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
      {result.variant_source === "upload" && result.missing_evidence?.length > 0 && (
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

function ReconciliationStage({ result }: { result: WorkupResult }) {
  const r = result.reconciliation;
  const concordant = r.status === "CONCORDANT";
  const cc = classColor(r.final_classification);

  return (
    <section className={`card p-6 ${concordant ? "card-glow-success" : "card-glow-warning"}`}>
      <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
        <GitMerge className="size-3.5" /> Step 4 &middot; AI vs ACMG reconciliation
      </h2>
      <div className="flex flex-wrap items-center gap-x-10 gap-y-4">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-muted">Status</p>
          <p className={`mt-1 flex items-center gap-2 text-2xl font-black ${concordant ? "text-success" : "text-warning"}`}>
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
        </>
      )}
    </section>
  );
}

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
  const tx = result.provenance?.tx_id ?? "";
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
      {tx && (
        <p className="mono mt-4 text-[10px] text-muted">
          sealed · tx {tx.slice(0, 18)}… · block #{result.provenance.block_index} ·{" "}
          {result.provenance.model_version}
        </p>
      )}
    </section>
  );
}
