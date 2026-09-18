"use client";

import type { InterpretationDiff, InterpretationVersion } from "@/lib/platform/types";
import { timestampLabel } from "@/lib/ui";
import { EmptyState, StatusBadge } from "@/components/platform/ui";

function DiffLine({ added, children }: { added?: boolean; children: string }) {
  return (
    <p
      className={`mono rounded-md px-2 py-1 text-xs ${
        added ? "bg-success/10 text-success" : "bg-error/10 text-error"
      }`}
    >
      {added ? "+ " : "− "}
      {children}
    </p>
  );
}

export default function InterpretationDiffView({
  versions,
  diff,
  a,
  b,
  onChangeA,
  onChangeB,
}: {
  versions: InterpretationVersion[];
  diff: InterpretationDiff | null;
  a: number;
  b: number;
  onChangeA: (v: number) => void;
  onChangeB: (v: number) => void;
}) {
  if (versions.length === 0) {
    return <EmptyState text="No previous interpretation versions" />;
  }
  const va = versions.find((v) => v.version === a);
  const vb = versions.find((v) => v.version === b);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {versions.map((v) => (
          <span key={v.version} className="rounded-lg border border-navy-950/10 px-3 py-1 text-xs font-semibold">
            Interpretation v{v.version}
          </span>
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-xs text-muted">
          Version A
          <select
            className="mt-1 w-full rounded-lg border border-navy-950/10 px-3 py-2 text-sm"
            value={a}
            onChange={(e) => onChangeA(Number(e.target.value))}
          >
            {versions.map((v) => (
              <option key={v.version} value={v.version}>
                v{v.version} · {v.classification}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-muted">
          Version B
          <select
            className="mt-1 w-full rounded-lg border border-navy-950/10 px-3 py-2 text-sm"
            value={b}
            onChange={(e) => onChangeB(Number(e.target.value))}
          >
            {versions.map((v) => (
              <option key={v.version} value={v.version}>
                v{v.version} · {v.classification}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {[va, vb].map((v, i) => (
          <div key={i} className="card p-4">
            <p className="text-[10px] uppercase tracking-widest text-muted">Version {v?.version ?? "—"}</p>
            <div className="mt-2">
              <StatusBadge label={v?.classification ?? "—"} />
            </div>
            <p className="mt-2 text-xs text-muted">
              Model {v?.model_version ?? "—"} · guideline {v?.guideline_version ?? "—"}
            </p>
            <p className="mt-1 text-xs text-muted">
              Reviewer {v?.reviewer ?? "—"} · {v ? timestampLabel(v.created_at) : "—"}
            </p>
          </div>
        ))}
      </div>
      {diff ? (
        <section className="card space-y-4 p-5">
          <h3 className="text-sm font-semibold">Classification change</h3>
          <p className="text-sm">
            {diff.changed_classification.before} → {diff.changed_classification.after}
          </p>
          <div>
            <h4 className="text-[10px] font-semibold uppercase tracking-widest text-muted">ACMG changes</h4>
            <div className="mt-2 space-y-1">
              {diff.changed_acmg_criteria.length === 0 && <p className="text-xs text-muted">No ACMG criterion changes.</p>}
              {diff.changed_acmg_criteria.map((c) => (
                <p key={c.criterion} className="text-xs">
                  {c.criterion}: {c.before ?? "—"} → {c.after ?? "—"}
                </p>
              ))}
            </div>
          </div>
          <div>
            <h4 className="text-[10px] font-semibold uppercase tracking-widest text-muted">ML changes</h4>
            <p className="text-xs">
              Probability {diff.changed_model_probability.before ?? "—"} → {diff.changed_model_probability.after ?? "—"}
            </p>
          </div>
          <div>
            <h4 className="text-[10px] font-semibold uppercase tracking-widest text-muted">Phenotype changes</h4>
            <p className="text-xs">
              Score {diff.changed_phenotype_score.before ?? "—"} → {diff.changed_phenotype_score.after ?? "—"}
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-muted">Evidence added</h4>
              {diff.new_evidence.length === 0 ? (
                <p className="text-xs text-muted">None</p>
              ) : (
                diff.new_evidence.map((id) => <DiffLine key={id} added>{id}</DiffLine>)
              )}
            </div>
            <div>
              <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-muted">Evidence removed</h4>
              {diff.removed_evidence.length === 0 ? (
                <p className="text-xs text-muted">None</p>
              ) : (
                diff.removed_evidence.map((id) => <DiffLine key={id}>{id}</DiffLine>)
              )}
            </div>
          </div>
          <p className="text-xs text-muted">{diff.summary}</p>
        </section>
      ) : (
        <EmptyState text="Select two versions to load a visual diff." />
      )}
    </div>
  );
}
