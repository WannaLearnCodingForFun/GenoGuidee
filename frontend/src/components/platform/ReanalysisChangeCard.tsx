"use client";

import Link from "next/link";
import type { ReanalysisChange } from "@/lib/platform/types";
import { timestampLabel } from "@/lib/ui";
import { StatusBadge } from "@/components/platform/ui";

export default function ReanalysisChangeCard({ change }: { change: ReanalysisChange }) {
  const payload = change.payload;
  const before = String(payload.classification_before ?? "—");
  const after = String(payload.classification_after ?? "—");
  const review = Boolean(payload.review_required);
  const sources = Array.isArray(payload.source_changes)
    ? (payload.source_changes as { source?: string }[]).map((s) => s.source).filter(Boolean)
    : [];
  return (
    <article className="card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="mono text-sm font-semibold">{change.variant_id ?? "Unassigned variant"}</p>
          <p className="mt-1 text-xs text-muted">{change.change_type}</p>
        </div>
        <StatusBadge label={review ? "Human review required" : "No classification change"} />
      </div>
      <p className="mt-3 text-sm">
        {before} <span className="text-muted">↓</span> {after}
      </p>
      <p className="mt-2 text-xs text-muted">
        Reason: {change.change_type === "NO_CHANGE" ? "No evidence fingerprint change" : "Evidence source update"}
      </p>
      <p className="mt-1 text-xs text-muted">
        Evidence changed: {sources.length ? sources.join(", ") : "None"}
      </p>
      <p className="mt-1 text-xs text-muted">Date: {timestampLabel(change.created_at)}</p>
      {change.interpretation_id && (
        <Link
          href={`/interpretations/${encodeURIComponent(change.interpretation_id)}`}
          className="mt-3 inline-block text-xs font-semibold text-cyan"
        >
          Open interpretation history →
        </Link>
      )}
    </article>
  );
}
