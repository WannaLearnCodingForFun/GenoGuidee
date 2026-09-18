"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Radar } from "lucide-react";
import { api, type AnalyzeResult, type VariantListItem } from "@/lib/api";
import { platformApi } from "@/lib/platform/client";
import { humanError } from "@/lib/platform/errors";
import { radarBodyFromAnalyze } from "@/lib/platform/radar";
import { writePlatformSession } from "@/lib/platform/session";
import type { EvidenceRadar, PlatformGraph } from "@/lib/platform/types";
import EvidenceGraph from "@/components/platform/EvidenceGraph";
import EvidenceRadarView from "@/components/platform/EvidenceRadar";
import EvidenceTable from "@/components/platform/EvidenceTable";
import { EmptyState, ErrorBanner, PageHeader, SkeletonCard, StatusBadge, ghostBtn, primaryBtn } from "@/components/platform/ui";

function EvidenceIntelligenceInner() {
  const search = useSearchParams();
  const queryVariant = search.get("variant");
  const [variants, setVariants] = useState<VariantListItem[]>([]);
  const [variantId, setVariantId] = useState("");
  const [analyze, setAnalyze] = useState<AnalyzeResult | null>(null);
  const [radar, setRadar] = useState<EvidenceRadar | null>(null);
  const [graph, setGraph] = useState<PlatformGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [graphLoading, setGraphLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projecting, setProjecting] = useState(false);

  const loadGraph = useCallback(async (id: string) => {
    setGraphLoading(true);
    try {
      const g = await platformApi.graph(`variant:${id}`);
      setGraph(g);
    } catch (e) {
      setError(humanError(e));
    } finally {
      setGraphLoading(false);
    }
  }, []);

  const run = useCallback(
    async (id: string) => {
      if (!id) return;
      setLoading(true);
      setError(null);
      writePlatformSession({ variantId: id });
      try {
        const result = await api.analyze(id);
        setAnalyze(result);
        const r = await platformApi.radar(radarBodyFromAnalyze(result));
        setRadar(r);
        await loadGraph(id);
      } catch (e) {
        setError(humanError(e));
      } finally {
        setLoading(false);
      }
    },
    [loadGraph],
  );

  useEffect(() => {
    api
      .variants()
      .then((rows) => {
        setVariants(rows);
        const initial = queryVariant || rows.find((v) => v.showcase)?.id || rows[0]?.id || "";
        setVariantId(initial);
        if (initial) void run(initial);
        else setLoading(false);
      })
      .catch((e) => {
        setError(humanError(e));
        setLoading(false);
      });
  }, [run, queryVariant]);

  async function projectEvidence() {
    if (!analyze) return;
    setProjecting(true);
    setError(null);
    const retrieved = new Date().toISOString();
    const vid = analyze.variant.id;
    try {
      await platformApi.addEdge({
        source_key: `variant:${vid}`,
        target_key: `gene:${analyze.variant.gene}`,
        edge_type: "VARIANT_IN_GENE",
        source_node: { type: "Variant", label: `${analyze.variant.gene} ${analyze.variant.hgvs_c}` },
        target_node: { type: "Gene", label: analyze.variant.gene },
      });
      for (const c of analyze.acmg.met) {
        await platformApi.addEdge({
          source_key: `variant:${vid}`,
          target_key: `evidence:${vid}:${c.id}`,
          edge_type: "VARIANT_HAS_EVIDENCE",
          source: "ACMG",
          source_id: c.id,
          source_version: analyze.acmg.framework,
          retrieved_at: retrieved,
          evidence_strength: c.strength,
          direction: "supporting",
          source_node: { type: "Variant", label: `${analyze.variant.gene} ${analyze.variant.hgvs_c}` },
          target_node: { type: "Evidence", label: c.id },
        });
      }
      await loadGraph(vid);
    } catch (e) {
      setError(humanError(e));
    } finally {
      setProjecting(false);
    }
  }

  const selected = variants.find((v) => v.id === variantId);

  return (
    <div className="mx-auto max-w-7xl px-6 py-10 sm:px-8">
      <PageHeader
        icon={Radar}
        title="Evidence Intelligence"
        subtitle="Trace every interpretation back to the evidence supporting it."
        actions={
          <div className="flex flex-wrap gap-2">
            <select
              className="rounded-lg border border-navy-950/10 px-3 py-2 text-sm"
              value={variantId}
              onChange={(e) => {
                setVariantId(e.target.value);
                void run(e.target.value);
              }}
            >
              {variants.length === 0 && <option value="">No variants</option>}
              {variants.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.gene} {v.hgvs_c}
                  {v.showcase_label ? ` · ${v.showcase_label}` : ""}
                </option>
              ))}
            </select>
            <button type="button" className={ghostBtn()} onClick={() => void run(variantId)}>
              Refresh
            </button>
            <button type="button" className={primaryBtn()} disabled={projecting || !analyze} onClick={() => void projectEvidence()}>
              Project ACMG evidence
            </button>
          </div>
        }
      />
      <ErrorBanner message={error} />
      {loading ? (
        <div className="grid gap-3 sm:grid-cols-4">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : (
        <>
          <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="card p-4">
              <p className="text-[10px] uppercase tracking-widest text-muted">Classification</p>
              <div className="mt-2">
                <StatusBadge label={analyze?.reconciliation.final_classification ?? "—"} />
              </div>
            </div>
            <div className="card p-4">
              <p className="text-[10px] uppercase tracking-widest text-muted">Confidence</p>
              <p className="mt-2 text-lg font-bold">{radar ? `${(radar.confidence * 100).toFixed(0)}%` : "—"}</p>
            </div>
            <div className="card p-4">
              <p className="text-[10px] uppercase tracking-widest text-muted">Evidence state</p>
              <div className="mt-2">
                <StatusBadge label={radar?.overall_state ?? "INSUFFICIENT"} />
              </div>
            </div>
            <div className="card p-4">
              <p className="text-[10px] uppercase tracking-widest text-muted">Human review</p>
              <p className="mt-2 text-sm font-semibold">
                {radar?.human_review_required || analyze?.reconciliation.status === "DISCORDANT"
                  ? "Human review required"
                  : "Not flagged"}
              </p>
            </div>
          </div>
          {analyze?.reconciliation.status === "DISCORDANT" && (
            <p className="mb-4 rounded-lg border border-warning/30 bg-warning/5 px-3 py-2 text-sm">
              ML ≠ ACMG — {analyze.ml.top_class} vs {analyze.acmg.classification}. ACMG remains authoritative.
            </p>
          )}
          {!radar && <EmptyState text="No evidence available" />}
          {radar && <EvidenceRadarView radar={radar} />}
          <div className="mt-4">{radar && <EvidenceTable items={radar.items} />}</div>
          <h2 className="mt-8 mb-3 text-sm font-semibold">Evidence graph</h2>
          <EvidenceGraph graph={graph} loading={graphLoading} />
          {selected && (
            <p className="mt-3 text-xs text-muted">
              Seed {selected.gene} {selected.hgvs_c}. Computational scores are shown as recorded annotations, not independent ACMG evidence.
            </p>
          )}
        </>
      )}
    </div>
  );
}

export default function EvidenceIntelligencePage() {
  return (
    <Suspense fallback={<div className="px-8 py-12 text-sm text-muted">Loading evidence workspace…</div>}>
      <EvidenceIntelligenceInner />
    </Suspense>
  );
}
