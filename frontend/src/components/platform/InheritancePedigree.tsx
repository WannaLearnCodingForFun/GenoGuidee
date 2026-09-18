"use client";

import type { InheritanceResult } from "@/lib/platform/types";
import { EmptyState, StatusBadge } from "@/components/platform/ui";

export interface PedigreeMember {
  variant_id: string;
  gene: string;
  chrom: string;
  zygosity: string;
}

const MODELS = [
  "Autosomal Dominant",
  "Autosomal Recessive",
  "De Novo",
  "Compound Heterozygous",
  "X-linked",
  "Mitochondrial",
];

export default function InheritancePedigree({
  members,
  onChange,
  result,
}: {
  members: Record<"mother" | "father" | "child" | "sibling", PedigreeMember>;
  onChange: (who: keyof typeof members, patch: Partial<PedigreeMember>) => void;
  result: InheritanceResult | null;
}) {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {(["mother", "father", "child", "sibling"] as const).map((who) => (
          <div key={who} className="card p-4">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-muted">{who}</p>
            <input
              className="mt-2 w-full rounded border border-navy-950/10 px-2 py-1 text-xs"
              placeholder="Variant ID"
              value={members[who].variant_id}
              onChange={(e) => onChange(who, { variant_id: e.target.value })}
            />
            <input
              className="mt-1 w-full rounded border border-navy-950/10 px-2 py-1 text-xs"
              placeholder="Gene"
              value={members[who].gene}
              onChange={(e) => onChange(who, { gene: e.target.value })}
            />
            <input
              className="mt-1 w-full rounded border border-navy-950/10 px-2 py-1 text-xs"
              placeholder="Chrom"
              value={members[who].chrom}
              onChange={(e) => onChange(who, { chrom: e.target.value })}
            />
            <input
              className="mt-1 w-full rounded border border-navy-950/10 px-2 py-1 text-xs"
              placeholder="Zygosity"
              value={members[who].zygosity}
              onChange={(e) => onChange(who, { zygosity: e.target.value })}
            />
          </div>
        ))}
      </div>
      <section className="card p-5">
        <h3 className="text-sm font-semibold">Candidate models</h3>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {MODELS.map((m) => (
            <span
              key={m}
              className={`rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${
                result && result.inheritance_model.replace(/_/g, " ").toLowerCase().includes(m.toLowerCase().split(" ")[0].toLowerCase())
                  ? "border-cyan/40 bg-cyan/10 text-cyan"
                  : "border-navy-950/10 text-muted"
              }`}
            >
              {m}
            </span>
          ))}
        </div>
        {!result && <div className="mt-3"><EmptyState text="No pedigree data submitted yet." /></div>}
        {result && (
          <div className="mt-4 space-y-2 text-sm">
            <p>
              Model: <strong>{result.inheritance_model.replace(/_/g, " ")}</strong>
            </p>
            <StatusBadge label={result.phase_status === "UNKNOWN" ? "PHASE UNKNOWN" : result.phase_status} />
            <p className="text-xs text-muted">Confidence {result.confidence} · {result.human_review_required ? "Human review required" : "Review not flagged"}</p>
            <ul className="list-disc pl-4 text-xs text-muted">
              {result.evidence.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
            <p className="text-xs text-muted">This is a candidate inheritance model, not a confirmed inheritance call.</p>
          </div>
        )}
      </section>
    </div>
  );
}
