"use client";

import type { ModelOODResult } from "@/lib/platform/types";
import { EmptyState, StatusBadge } from "@/components/platform/ui";

export default function OODPanel({ ood }: { ood: ModelOODResult | null }) {
  if (!ood) {
    return <EmptyState text="No monitoring observations available yet. Run an inference batch to begin monitoring." />;
  }
  const state = ood.OOD_state ?? "UNCERTAIN";
  return (
    <section className="card p-5">
      <h2 className="text-sm font-semibold">OOD panel</h2>
      <div className="mt-3 flex flex-wrap gap-2">
        {["IN_DISTRIBUTION", "LOW_CONFIDENCE", "OUT_OF_DISTRIBUTION"].map((s) => (
          <span key={s} className={s === state ? "" : "opacity-40"}>
            <StatusBadge label={s.replace("LOW_CONFIDENCE", "UNCERTAIN")} />
          </span>
        ))}
      </div>
      <p className="mt-3 text-xs text-muted">Highlighted state is the backend OOD_state: {state}</p>
      <dl className="mt-3 grid gap-2 sm:grid-cols-2 text-sm">
        <div>
          <dt className="text-[10px] uppercase tracking-widest text-muted">OOD score</dt>
          <dd className="mono">{ood.OOD_score ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-widest text-muted">Threshold</dt>
          <dd className="text-xs text-muted">Backend uses max-probability cutoffs 0.55 / 0.40 when no stored OOD distance is present.</dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-widest text-muted">Reason</dt>
          <dd>{ood.reason ?? state}</dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-widest text-muted">Recommended action</dt>
          <dd>{ood.human_review_required ? "Human review required" : "No review flag from OOD"}</dd>
        </div>
      </dl>
    </section>
  );
}
