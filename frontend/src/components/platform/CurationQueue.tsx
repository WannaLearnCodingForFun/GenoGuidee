"use client";

import type { InterpretationVersion } from "@/lib/platform/types";
import { timestampLabel } from "@/lib/ui";
import { EmptyState, StatusBadge } from "@/components/platform/ui";

export const CURATION_QUEUES = [
  "AI_DRAFT",
  "NEEDS_REVIEW",
  "CONFLICTING",
  "PENDING_APPROVAL",
  "FINALIZED",
] as const;

export type CurationQueueId = (typeof CURATION_QUEUES)[number];

export function queueFor(v: InterpretationVersion): CurationQueueId {
  const state = (v.curation_state || "AI_DRAFT").toUpperCase();
  if (state === "FINALIZED") return "FINALIZED";
  if (state === "SUPERSEDED") return "FINALIZED";
  if (state === "LAB_REVIEW" || state === "NEEDS_REVIEW") return "NEEDS_REVIEW";
  if (state === "PENDING_APPROVAL" || state === "SIGN_OFF") return "PENDING_APPROVAL";
  const recon = v.payload?.reconciliation;
  const hr = v.payload?.human_review;
  if (hr === true || (recon && typeof recon === "object" && (recon as { status?: string }).status === "DISCORDANT")) {
    return "CONFLICTING";
  }
  return "AI_DRAFT";
}

const LABELS: Record<CurationQueueId, string> = {
  AI_DRAFT: "AI Drafts",
  NEEDS_REVIEW: "Needs Review",
  CONFLICTING: "Conflicting Evidence",
  PENDING_APPROVAL: "Pending Approval",
  FINALIZED: "Finalized",
};

export default function CurationQueue({
  latest,
  activeQueue,
  selectedId,
  onQueue,
  onSelect,
}: {
  latest: InterpretationVersion[];
  activeQueue: CurationQueueId;
  selectedId: string | null;
  onQueue: (q: CurationQueueId) => void;
  onSelect: (id: string) => void;
}) {
  const grouped = CURATION_QUEUES.map((q) => ({
    q,
    items: latest.filter((v) => queueFor(v) === q),
  }));
  const shown = grouped.find((g) => g.q === activeQueue)?.items ?? [];

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {grouped.map(({ q, items }) => (
          <button
            key={q}
            type="button"
            onClick={() => onQueue(q)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-semibold ${
              activeQueue === q ? "border-cyan/50 bg-cyan/10 text-cyan" : "border-navy-950/10 text-muted"
            }`}
          >
            {LABELS[q]} ({items.length})
          </button>
        ))}
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {shown.length === 0 && <EmptyState text="No pending curation cases in this queue." />}
        {shown.map((item) => (
          <button
            key={item.interpretation_id}
            type="button"
            onClick={() => onSelect(item.interpretation_id)}
            className={`card p-4 text-left ${selectedId === item.interpretation_id ? "card-glow-cyan" : ""}`}
          >
            <p className="mono text-xs text-muted">{item.interpretation_id}</p>
            <p className="mt-1 font-semibold">{item.variant_id ?? "Variant not recorded"}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <StatusBadge label={item.classification} />
              <StatusBadge label={item.curation_state} />
            </div>
            <p className="mt-2 text-xs text-muted">Assigned reviewer: {item.reviewer ?? "Unassigned"}</p>
            <p className="text-xs text-muted">Last updated: {timestampLabel(item.created_at)}</p>
          </button>
        ))}
      </div>
    </div>
  );
}
