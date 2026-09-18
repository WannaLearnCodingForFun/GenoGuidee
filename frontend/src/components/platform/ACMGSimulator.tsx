"use client";

import { useMemo, useState } from "react";
import type { ACMGEvaluateResult, ACMGSimulation } from "@/lib/platform/types";
import { EmptyState, StatusBadge, ghostBtn, primaryBtn } from "@/components/platform/ui";

export default function ACMGSimulator({
  official,
  simulation,
  onSimulate,
  busy,
}: {
  official: ACMGEvaluateResult | { classification: string; met_criteria: string[]; criteria: { id: string; name: string; status: string; category?: string; default_strength?: string; applied_strength?: string | null; reason?: string; sources?: string[] }[] } | null;
  simulation: ACMGSimulation | null;
  onSimulate: (mods: Record<string, unknown>[]) => void;
  busy?: boolean;
}) {
  const [mods, setMods] = useState<Record<string, unknown>[]>([]);
  const [cid, setCid] = useState("PP3");
  const [strength, setStrength] = useState("SUPPORTING");
  const criteria = useMemo(() => official?.criteria ?? [], [official]);
  const ids = useMemo(() => criteria.map((c) => c.id), [criteria]);

  if (!official) return <EmptyState text="Load an official ACMG evaluation to simulate." />;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-warning/40 bg-warning/10 px-4 py-3 text-sm font-semibold text-warning">
        SIMULATION — NOT OFFICIAL INTERPRETATION
      </div>
      <section className="card p-5">
        <h3 className="text-sm font-semibold">Current criteria</h3>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {criteria.map((c) => (
            <div key={c.id} className="rounded-lg border border-navy-950/10 p-3 text-xs">
              <p className="mono font-semibold">{c.id}</p>
              <p>{c.name}</p>
              <p className="mt-1 text-muted">Status {c.status}</p>
              <p className="text-muted">Strength {c.applied_strength ?? c.default_strength ?? "—"}</p>
              <p className="text-muted">Source {(c.sources ?? []).join(", ") || "evaluator"}</p>
            </div>
          ))}
        </div>
      </section>
      <section className="card space-y-3 p-5">
        <h3 className="text-sm font-semibold">Hypothetical actions</h3>
        <div className="flex flex-wrap gap-2">
          <select className="rounded-lg border border-navy-950/10 px-2 py-1 text-xs" value={cid} onChange={(e) => setCid(e.target.value)}>
            {(ids.length ? ids : ["PVS1", "PS1", "PS3", "PM2", "PP3", "BA1", "BS1", "BP4"]).map((id) => (
              <option key={id}>{id}</option>
            ))}
          </select>
          <select className="rounded-lg border border-navy-950/10 px-2 py-1 text-xs" value={strength} onChange={(e) => setStrength(e.target.value)}>
            {["SUPPORTING", "MODERATE", "STRONG", "VERY_STRONG"].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
          <button type="button" className={ghostBtn()} onClick={() => setMods((m) => [...m, { op: "add", criterion: cid, strength }])}>
            Add criterion
          </button>
          <button type="button" className={ghostBtn()} onClick={() => setMods((m) => [...m, { op: "remove", criterion: cid }])}>
            Remove criterion
          </button>
          <button type="button" className={ghostBtn()} onClick={() => setMods((m) => [...m, { op: "upgrade", criterion: cid }])}>
            Change strength (upgrade)
          </button>
          <button type="button" className={ghostBtn()} onClick={() => setMods((m) => [...m, { op: "downgrade", criterion: cid }])}>
            Change strength (downgrade)
          </button>
        </div>
        <ul className="text-xs text-muted">
          {mods.map((m, i) => (
            <li key={i}>{JSON.stringify(m)}</li>
          ))}
        </ul>
        <button type="button" disabled={busy} className={primaryBtn()} onClick={() => onSimulate(mods)}>
          Simulate
        </button>
      </section>
      {simulation && (
        <section className="card p-5">
          <div className="flex flex-wrap gap-3">
            <div>
              <p className="text-[10px] uppercase tracking-widest text-muted">Official classification</p>
              <StatusBadge label={simulation.official_classification ?? "—"} />
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-widest text-muted">Simulated classification</p>
              <StatusBadge label={simulation.simulated_classification} />
            </div>
          </div>
          <p className="mt-3 text-sm">
            Difference:{" "}
            {(simulation.official_classification ?? "—") === simulation.simulated_classification
              ? "No classification change"
              : `${simulation.official_classification ?? "—"} → ${simulation.simulated_classification}`}
          </p>
          <p className="mt-2 text-xs text-muted">{simulation.combining_rationale}</p>
          <p className="mt-2 text-xs text-muted">{simulation.note}</p>
        </section>
      )}
    </div>
  );
}
