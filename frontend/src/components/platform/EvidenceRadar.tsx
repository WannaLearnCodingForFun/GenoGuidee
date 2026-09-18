"use client";

import { useMemo, useState } from "react";
import type { EvidenceRadar, RadarItem } from "@/lib/platform/types";
import { categoryLabel, itemDetailText } from "@/lib/platform/radar";
import { EmptyState, StatusBadge } from "@/components/platform/ui";

function Lane({ title, items, onPick }: { title: string; items: RadarItem[]; onPick: (i: RadarItem) => void }) {
  return (
    <div className="min-w-0">
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-muted">{title}</p>
      <div className="space-y-1.5">
        {items.length === 0 && <p className="text-xs text-muted">None</p>}
        {items.map((item) => (
          <button
            key={`${item.source}-${item.name}`}
            type="button"
            onClick={() => onPick(item)}
            className="block w-full rounded-lg border border-navy-950/10 px-2 py-1.5 text-left text-xs hover:border-cyan/30"
          >
            <span className="font-semibold">{item.source}</span>
            <span className="ml-2 text-muted">{item.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export default function EvidenceRadar({ radar, onSelect }: { radar: EvidenceRadar | null; onSelect?: (item: RadarItem) => void }) {
  const [open, setOpen] = useState<RadarItem | null>(null);
  const named = useMemo(() => {
    const items = radar?.items ?? [];
    const pick = (n: string) => items.find((i) => i.name === n);
    return {
      clinvar: pick("clinvar"),
      acmg: pick("acmg"),
      ml: pick("ml"),
    };
  }, [radar]);

  if (!radar) {
    return <EmptyState text="No evidence available" />;
  }

  function pick(item: RadarItem) {
    setOpen(item);
    onSelect?.(item);
  }

  return (
    <section className="card p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Evidence Conflict Radar</h2>
        <StatusBadge label={radar.overall_state} />
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {(["ClinVar", "ACMG", "ML"] as const).map((label) => {
          const item = label === "ClinVar" ? named.clinvar : label === "ACMG" ? named.acmg : named.ml;
          return (
            <button
              key={label}
              type="button"
              onClick={() => item && pick(item)}
              className="rounded-xl border border-navy-950/10 px-3 py-4 text-center"
            >
              <p className="text-[10px] uppercase tracking-widest text-muted">{label}</p>
              <p className="mt-2 font-semibold">{item ? categoryLabel(item.category) : "MISSING"}</p>
              <p className="mt-1 truncate text-xs text-muted">{item ? itemDetailText(item) : "Source not provided"}</p>
            </button>
          );
        })}
      </div>
      <p className="mt-4 text-center text-[10px] font-semibold uppercase tracking-[0.2em] text-muted">Reconciliation</p>
      <p className="mt-1 text-center text-sm">
        {radar.human_review_required ? "Human review required" : "Evidence state recorded"} · confidence{" "}
        {(radar.confidence * 100).toFixed(0)}%
      </p>
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <Lane title="Supporting" items={radar.supporting_evidence} onPick={pick} />
        <Lane title="Contradicting" items={radar.contradicting_evidence} onPick={pick} />
      </div>
      {open && (
        <div className="mt-4 rounded-xl border border-cyan/20 bg-cyan/5 p-4 text-sm">
          <p className="text-[10px] uppercase tracking-widest text-muted">Evidence detail</p>
          <dl className="mt-2 grid gap-2 sm:grid-cols-2">
            <div>
              <dt className="text-[10px] uppercase tracking-widest text-muted">Source</dt>
              <dd>{open.source}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-widest text-muted">Source ID</dt>
              <dd className="mono">{open.name}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-widest text-muted">Direction</dt>
              <dd>{categoryLabel(open.category)}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-widest text-muted">Strength / value</dt>
              <dd className="break-all">{itemDetailText(open)}</dd>
            </div>
          </dl>
        </div>
      )}
      {radar.note && <p className="mt-3 text-xs text-muted">{radar.note}</p>}
    </section>
  );
}
