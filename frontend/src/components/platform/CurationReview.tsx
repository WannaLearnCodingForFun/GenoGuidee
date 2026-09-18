"use client";

import { useState } from "react";
import type { Role } from "@/lib/useAccount";
import type { InterpretationVersion } from "@/lib/platform/types";
import { platformApi } from "@/lib/platform/client";
import { humanError } from "@/lib/platform/errors";
import { EmptyState, ErrorBanner, StatusBadge, ghostBtn, primaryBtn } from "@/components/platform/ui";

export default function CurationReview({
  current,
  events,
  role,
  onRefresh,
}: {
  current: InterpretationVersion | null;
  events: Record<string, unknown>[];
  role: Role;
  onRefresh: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [criterion, setCriterion] = useState("PVS1");
  const canCurate = role === "doctor" || role === "lab_technician";
  const canFinalize = canCurate;

  if (!current) return <EmptyState text="Select a case to open the review view." />;

  const acmg = current.acmg_criteria;
  const criteria = Array.isArray(acmg.criteria) ? acmg.criteria : [];
  const recon = current.payload.reconciliation;
  const ml = current.ml_prediction;

  async function act(body: Record<string, unknown>, label: string) {
    if (!current) return;
    setBusy(label);
    setError(null);
    try {
      await platformApi.curation({ interpretation_id: current.interpretation_id, ...body }, role);
      onRefresh();
    } catch (e) {
      setError(humanError(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <ErrorBanner message={error} />
      <section className="card p-5">
        <h3 className="text-sm font-semibold">Variant overview</h3>
        <p className="mono mt-1 text-sm">{current.variant_id ?? "—"}</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <StatusBadge label={current.classification} />
          <StatusBadge label={current.curation_state} />
        </div>
      </section>
      <section className="card p-5">
        <h3 className="text-sm font-semibold">AI interpretation</h3>
        <p className="mt-1 text-sm text-muted">
          Model {current.model_version ?? "—"} · top class{" "}
          {typeof ml?.top_class === "string" ? ml.top_class : "—"}
        </p>
        {recon != null && typeof recon === "object" ? (
          <p className="mt-1 text-xs text-muted">{JSON.stringify(recon)}</p>
        ) : null}
      </section>
      <section className="card p-5">
        <h3 className="text-sm font-semibold">ACMG evidence</h3>
        <ul className="mt-2 space-y-1 text-xs">
          {criteria.length === 0 && <li className="text-muted">No ACMG criteria on this version.</li>}
          {criteria.map((c) => {
            const row = c as Record<string, unknown>;
            return (
              <li key={String(row.id)} className="flex justify-between gap-2 border-b border-navy-950/5 py-1">
                <span className="mono">{String(row.id)}</span>
                <span>{String(row.status ?? row.applied_strength ?? "")}</span>
              </li>
            );
          })}
        </ul>
      </section>
      <section className="card p-5">
        <h3 className="text-sm font-semibold">Evidence sources</h3>
        <p className="mt-1 text-xs text-muted">{current.evidence_ids.join(", ") || "No evidence IDs recorded."}</p>
      </section>
      <section className="card p-5">
        <h3 className="text-sm font-semibold">Phenotype context / inheritance / model confidence</h3>
        <p className="mt-1 text-xs text-muted">
          Phenotype score {current.phenotype_score ?? "—"} · guideline {current.guideline_version ?? "—"}
        </p>
      </section>
      <section className="card p-5">
        <h3 className="text-sm font-semibold">Previous interpretations / provenance</h3>
        <p className="mt-1 text-xs text-muted">
          KG {current.kg_version ?? "—"} · version {current.version}
        </p>
        <ul className="mt-2 space-y-1 text-xs text-muted">
          {events.length === 0 && <li>No curation events yet.</li>}
          {events.map((ev, i) => (
            <li key={i}>{JSON.stringify(ev)}</li>
          ))}
        </ul>
      </section>
      {canCurate ? (
        <section className="card space-y-3 p-5">
          <h3 className="text-sm font-semibold">Review actions</h3>
          <p className="text-xs text-muted">Backend authorization remains authoritative. Failed actions show the API error.</p>
          <div className="flex flex-wrap gap-2">
            <input
              className="rounded-lg border border-navy-950/10 px-2 py-1 text-xs"
              value={criterion}
              onChange={(e) => setCriterion(e.target.value)}
              placeholder="Criterion"
            />
            <button type="button" disabled={!!busy} className={ghostBtn()} onClick={() => act({ action: "accept", criterion_id: criterion, reason: "accept evidence" }, "accept")}>
              Accept Evidence
            </button>
            <button type="button" disabled={!!busy} className={ghostBtn()} onClick={() => act({ action: "reject", criterion_id: criterion, reason: "reject evidence" }, "reject")}>
              Reject Evidence
            </button>
            <button type="button" disabled={!!busy} className={ghostBtn()} onClick={() => act({ action: "change_evidence", criterion_id: criterion, new_status: "MET", reason: "modify evidence" }, "modify")}>
              Modify Evidence
            </button>
            <button type="button" disabled={!!busy} className={ghostBtn()} onClick={() => act({ action: "request_review", state: "LAB_REVIEW", reason: "request review" }, "review")}>
              Request Review
            </button>
            {canFinalize && (
              <>
                <button type="button" disabled={!!busy} className={primaryBtn()} onClick={() => act({ action: "finalize", reason: "finalize" }, "finalize")}>
                  Finalize
                </button>
                <button type="button" disabled={!!busy} className={ghostBtn()} onClick={() => act({ action: "supersede", reason: "supersede" }, "supersede")}>
                  Supersede
                </button>
              </>
            )}
          </div>
          <div className="flex gap-2">
            <input
              className="flex-1 rounded-lg border border-navy-950/10 px-3 py-2 text-sm"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Add evidence comment"
            />
            <button
              type="button"
              disabled={!!busy || !comment}
              className={ghostBtn()}
              onClick={() => act({ action: "comment", comment, reason: "comment" }, "comment")}
            >
              Add Evidence
            </button>
          </div>
          {busy && <p className="text-xs text-muted">Working: {busy}…</p>}
        </section>
      ) : (
        <EmptyState text="Your role cannot submit curation actions." />
      )}
    </div>
  );
}
