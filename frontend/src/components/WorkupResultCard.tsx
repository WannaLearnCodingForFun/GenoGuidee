"use client";

import { Activity, BrainCircuit, GitMerge, Pill, Scale } from "lucide-react";
import type { WorkupSnapshot } from "@/lib/api";
import { classColor } from "@/lib/ui";

const PLAIN_STATUS: Record<string, string> = {
  pathogenic: "A significant finding was identified and is being reviewed with your care team.",
  likely_pathogenic: "A likely significant finding was identified and is being reviewed with your care team.",
  benign: "No significant finding was identified in this result.",
  likely_benign: "No significant finding was identified in this result.",
  vus: "This result needs further review before a finding can be confirmed.",
};

function plainStatus(classification: string | null | undefined): string {
  const key = (classification ?? "").toLowerCase().replace(/[\s-]+/g, "_");
  return PLAIN_STATUS[key] ?? "Your care team has recorded a clinical workup for review.";
}

export function WorkupResultCard({
  workup,
  audience,
}: {
  workup: WorkupSnapshot;
  audience: "patient" | "clinician";
}) {
  const payload = workup.payload;
  const variant = payload?.variant;
  const gene = workup.gene ?? variant?.gene ?? "—";
  const hgvs = workup.hgvs_c ?? variant?.hgvs_c ?? "";
  const acmg = workup.acmg_classification ?? payload?.acmg?.classification ?? "—";
  const ml = workup.ml_top_class ?? payload?.ml?.top_class ?? "—";
  const final = workup.final_classification ?? payload?.reconciliation?.final_classification ?? acmg;
  const recon = workup.reconciliation_status ?? payload?.reconciliation?.status ?? "—";
  const cc = classColor(final);
  const when = workup.created_at
    ? new Date(workup.created_at * 1000).toLocaleString()
    : null;

  if (audience === "patient") {
    return (
      <div className="space-y-3">
        <p className="text-sm">
          <span className="font-semibold">{gene}</span>{" "}
          {hgvs && <span className="font-mono text-cyan">{hgvs}</span>}
        </p>
        <p className="text-sm">{plainStatus(final)}</p>
        {payload?.stages?.length ? (
          <ul className="space-y-1 text-xs text-muted">
            {payload.stages.map((s) => (
              <li key={s.id} className="flex justify-between gap-3">
                <span>{s.label}</span>
                <span className="uppercase tracking-widest">{s.status}</span>
              </li>
            ))}
          </ul>
        ) : null}
        {when && <p className="text-[11px] text-muted">Recorded {when}</p>}
        <p className="text-[11px] text-muted">
          Research prototype — not a diagnosis. Your care team reviews this result.
        </p>
      </div>
    );
  }

  return (
    <section className="card mt-4 p-5">
      <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
        <Activity className="size-4 text-cyan" /> Clinical workup result
      </h2>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-lg font-bold">
            {gene} {hgvs && <span className="font-mono text-base font-medium text-cyan">{hgvs}</span>}
          </p>
          <p className="mt-1 text-xs text-muted">
            {payload?.triple?.gene_disease ?? variant?.condition ?? "No curated condition listed"}
            {when ? ` · ${when}` : ""}
          </p>
        </div>
        <span className={`rounded border px-2 py-1 text-[10px] font-bold ${cc.border} ${cc.bg} ${cc.text}`}>
          ACMG {final}
        </span>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <div className="rounded-xl border border-navy-950/10 bg-panel2 p-3">
          <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted">
            <Scale className="size-3.5" /> ACMG
          </p>
          <p className="mt-1 text-sm font-semibold">{acmg}</p>
        </div>
        <div className="rounded-xl border border-navy-950/10 bg-panel2 p-3">
          <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted">
            <BrainCircuit className="size-3.5" /> Advisory model
          </p>
          <p className="mt-1 text-sm font-semibold">{ml}</p>
        </div>
        <div className="rounded-xl border border-navy-950/10 bg-panel2 p-3">
          <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted">
            <GitMerge className="size-3.5" /> Reconciliation
          </p>
          <p className="mt-1 text-sm font-semibold">{recon}</p>
          <p className="mt-1 text-[11px] text-muted">ACMG is authoritative. The model does not override it.</p>
        </div>
      </div>

      {payload?.stages?.length ? (
        <ol className="mt-4 grid gap-2 sm:grid-cols-5">
          {payload.stages.map((s) => (
            <li key={s.id} className="rounded-lg border border-navy-950/10 bg-panel2 px-3 py-2">
              <p className="text-[10px] uppercase tracking-widest text-muted">{s.label}</p>
              <p className="mt-0.5 text-xs font-semibold">{s.status}</p>
            </li>
          ))}
        </ol>
      ) : null}

      {payload?.medication && (
        <div className="mt-4 rounded-xl border border-navy-950/10 bg-panel2 p-3">
          <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted">
            <Pill className="size-3.5" /> Medication stage
          </p>
          <p className="mt-1 text-sm">{payload.medication.availability}</p>
          {payload.medication.reason && (
            <p className="mt-1 text-xs text-muted">{payload.medication.reason}</p>
          )}
        </div>
      )}

      {payload?.considerations?.length ? (
        <ul className="mt-4 space-y-2">
          {payload.considerations.map((c, i) => (
            <li key={`${c.type}-${i}`} className="rounded-lg border border-navy-950/10 bg-panel2 px-3 py-2 text-xs text-muted">
              <span className="mr-2 uppercase tracking-widest">{c.type}</span>
              {c.text}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
