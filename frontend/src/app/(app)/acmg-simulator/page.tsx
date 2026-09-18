"use client";

import { useEffect, useState } from "react";
import { GitCompare } from "lucide-react";
import { api, type AnalyzeResult, type VariantListItem } from "@/lib/api";
import { platformApi } from "@/lib/platform/client";
import { humanError } from "@/lib/platform/errors";
import type { ACMGSimulation } from "@/lib/platform/types";
import ACMGSimulator from "@/components/platform/ACMGSimulator";
import { ErrorBanner, PageHeader } from "@/components/platform/ui";

export default function ACMGSimulatorPage() {
  const [variants, setVariants] = useState<VariantListItem[]>([]);
  const [variantId, setVariantId] = useState("");
  const [official, setOfficial] = useState<AnalyzeResult["acmg"] | null>(null);
  const [simulation, setSimulation] = useState<ACMGSimulation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .variants()
      .then((rows) => {
        setVariants(rows);
        const initial = rows.find((v) => v.showcase)?.id || rows[0]?.id || "";
        setVariantId(initial);
        if (initial) void load(initial);
      })
      .catch((e) => setError(humanError(e)));
  }, []);

  async function load(id: string) {
    setBusy(true);
    setError(null);
    try {
      const result = await api.analyze(id);
      setOfficial(result.acmg);
      setSimulation(null);
    } catch (e) {
      setError(humanError(e));
    } finally {
      setBusy(false);
    }
  }

  async function simulate(mods: Record<string, unknown>[]) {
    if (!official) return;
    setBusy(true);
    setError(null);
    try {
      const sim = await platformApi.acmgSimulate(
        {
          classification: official.classification,
          met_criteria: official.met_criteria,
          criteria: official.criteria,
        },
        mods,
      );
      setSimulation(sim);
    } catch (e) {
      setError(humanError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-10 sm:px-8">
      <PageHeader
        icon={GitCompare}
        title="ACMG Evidence Simulator"
        subtitle="Explore how evidence changes classification without changing the official interpretation."
        actions={
          <select
            className="rounded-lg border border-navy-950/10 px-3 py-2 text-sm"
            value={variantId}
            onChange={(e) => {
              setVariantId(e.target.value);
              void load(e.target.value);
            }}
          >
            {variants.map((v) => (
              <option key={v.id} value={v.id}>
                {v.gene} {v.hgvs_c}
              </option>
            ))}
          </select>
        }
      />
      <ErrorBanner message={error} />
      <ACMGSimulator official={official} simulation={simulation} onSimulate={(m) => void simulate(m)} busy={busy} />
    </div>
  );
}
