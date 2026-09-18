"use client";

import { fieldClass, ghostBtn } from "@/components/platform/ui";

export interface PhenotypeDraft {
  key: string;
  term: string;
  negated: boolean;
  onset: string;
  severity: string;
}

export default function PhenotypeSelector({
  query,
  onQuery,
  drafts,
  onAdd,
  onRemove,
  onPatch,
}: {
  query: string;
  onQuery: (v: string) => void;
  drafts: PhenotypeDraft[];
  onAdd: () => void;
  onRemove: (key: string) => void;
  onPatch: (key: string, patch: Partial<PhenotypeDraft>) => void;
}) {
  return (
    <section className="card p-5">
      <h2 className="text-sm font-semibold">Search HPO term</h2>
      <p className="mt-1 text-xs text-muted">
        Phenotypic compatibility is used for prioritization, not a confirmed diagnosis.
      </p>
      <div className="mt-3 flex gap-2">
        <input className={fieldClass()} value={query} onChange={(e) => onQuery(e.target.value)} placeholder="HP:0001250 or seizure" />
        <button type="button" className={ghostBtn()} onClick={onAdd}>
          Add phenotype
        </button>
      </div>
      <ul className="mt-4 space-y-2">
        {drafts.map((d) => (
          <li key={d.key} className="rounded-lg border border-navy-950/10 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-semibold">{d.term}</p>
              <button type="button" className="text-xs text-error" onClick={() => onRemove(d.key)}>
                Remove phenotype
              </button>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              <label className="flex items-center gap-1">
                <input type="checkbox" checked={d.negated} onChange={(e) => onPatch(d.key, { negated: e.target.checked })} />
                Mark absent
              </label>
              <input
                className="rounded border border-navy-950/10 px-2 py-1"
                placeholder="Onset"
                value={d.onset}
                onChange={(e) => onPatch(d.key, { onset: e.target.value })}
              />
              <input
                className="rounded border border-navy-950/10 px-2 py-1"
                placeholder="Severity"
                value={d.severity}
                onChange={(e) => onPatch(d.key, { severity: e.target.value })}
              />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
