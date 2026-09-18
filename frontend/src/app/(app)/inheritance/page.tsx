"use client";

import { useState } from "react";
import { Users } from "lucide-react";
import { platformApi } from "@/lib/platform/client";
import { humanError } from "@/lib/platform/errors";
import type { InheritanceResult } from "@/lib/platform/types";
import InheritancePedigree, { type PedigreeMember } from "@/components/platform/InheritancePedigree";
import { ErrorBanner, PageHeader, primaryBtn } from "@/components/platform/ui";

const empty = (): PedigreeMember => ({ variant_id: "", gene: "", chrom: "", zygosity: "" });

function asVariants(m: PedigreeMember) {
  if (!m.variant_id) return [];
  return [
    {
      variant_id: m.variant_id,
      id: m.variant_id,
      gene: m.gene || undefined,
      chrom: m.chrom || undefined,
      chromosome: m.chrom || undefined,
      zygosity: m.zygosity || "UNKNOWN",
    },
  ];
}

export default function InheritancePage() {
  const [members, setMembers] = useState({
    mother: empty(),
    father: empty(),
    child: empty(),
    sibling: empty(),
  });
  const [result, setResult] = useState<InheritanceResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function solve() {
    setBusy(true);
    setError(null);
    try {
      const child = asVariants(members.child);
      if (child.length === 0) {
        setError("Enter a child variant before solving inheritance.");
        setBusy(false);
        return;
      }
      const r = await platformApi.inheritanceSolve({
        child,
        mother: asVariants(members.mother),
        father: asVariants(members.father),
        siblings: asVariants(members.sibling).length ? [asVariants(members.sibling)] : [],
      });
      setResult(r);
    } catch (e) {
      setError(humanError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-10 sm:px-8">
      <PageHeader
        icon={Users}
        title="Inheritance Solver"
        subtitle="Candidate inheritance models from submitted genotypes. Phase is never inferred without evidence."
        actions={
          <button type="button" className={primaryBtn()} disabled={busy} onClick={() => void solve()}>
            Solve
          </button>
        }
      />
      <ErrorBanner message={error} />
      <InheritancePedigree
        members={members}
        onChange={(who, patch) => setMembers((m) => ({ ...m, [who]: { ...m[who], ...patch } }))}
        result={result}
      />
    </div>
  );
}
