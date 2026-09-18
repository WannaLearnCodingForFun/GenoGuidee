"use client";

import { useMemo, useState } from "react";
import type { EvidenceFilter, RadarItem } from "@/lib/platform/types";
import { categoryLabel, evidenceFilter, itemDetailText } from "@/lib/platform/radar";
import { EmptyState } from "@/components/platform/ui";

const FILTERS: EvidenceFilter[] = ["All", "Supporting", "Contradicting", "Uncertain", "Missing"];

export default function EvidenceTable({ items }: { items: RadarItem[] }) {
  const [filter, setFilter] = useState<EvidenceFilter>("All");
  const rows = useMemo(
    () => items.filter((i) => filter === "All" || evidenceFilter(i.category) === filter),
    [items, filter],
  );

  return (
    <section className="card overflow-x-auto p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Evidence table</h2>
        <div className="flex flex-wrap gap-1">
          {FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              className={`rounded-lg border px-3 py-1 text-xs font-semibold ${
                filter === f ? "border-cyan/50 bg-cyan/10 text-cyan" : "border-navy-950/10 text-muted"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>
      {rows.length === 0 ? (
        <EmptyState text="No evidence available for this filter." />
      ) : (
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="text-[10px] uppercase tracking-widest text-muted">
            <tr>
              <th className="pb-2">Source</th>
              <th className="pb-2">Evidence</th>
              <th className="pb-2">Direction</th>
              <th className="pb-2">Strength</th>
              <th className="pb-2">Version</th>
              <th className="pb-2">Updated</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.source}-${row.name}`} className="border-t border-navy-950/8">
                <td className="py-2">{row.source}</td>
                <td className="mono py-2">{row.name}</td>
                <td className="py-2">{categoryLabel(row.category)}</td>
                <td className="max-w-[220px] truncate py-2 text-muted">{itemDetailText(row)}</td>
                <td className="py-2 text-muted">—</td>
                <td className="py-2 text-muted">—</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
