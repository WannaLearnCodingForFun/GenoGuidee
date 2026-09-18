"use client";

import type { DriftSnapshot } from "@/lib/platform/types";
import { DriftBadge, EmptyState } from "@/components/platform/ui";

export default function DriftPanel({ snap }: { snap: DriftSnapshot | null }) {
  if (!snap || snap.n === 0) {
    return <EmptyState text="No monitoring observations available yet. Run an inference batch to begin monitoring." />;
  }
  const tv = snap.total_variation ?? 0;
  const rows: { label: string; value: string }[] = [
    { label: "Feature drift", value: tv > 0.35 ? "HIGH" : tv > 0.15 ? "MODERATE" : "LOW" },
    { label: "Prediction drift", value: snap.drift_level },
    { label: "Population shift", value: snap.ood_rate != null && snap.ood_rate > 0.2 ? "HIGH" : snap.ood_rate != null && snap.ood_rate > 0.08 ? "MODERATE" : "LOW" },
    { label: "Variant-type shift", value: snap.gene_distribution?.length ? `${snap.gene_distribution.length} genes observed` : "Not reported" },
    { label: "Missingness shift", value: snap.missingness != null ? String(snap.missingness) : "—" },
  ];
  return (
    <section className="card p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold">Drift panel</h2>
        <DriftBadge level={snap.drift_level} />
      </div>
      <ul className="space-y-2 text-sm">
        {rows.map((r) => (
          <li key={r.label} className="flex justify-between gap-2">
            <span>{r.label}</span>
            <span className="text-muted">{r.value}</span>
          </li>
        ))}
      </ul>
      {snap.action && <p className="mt-3 text-xs text-muted">Recommended action: {snap.action}. Retrained: {snap.retrained ? "yes" : "no"}.</p>}
    </section>
  );
}
