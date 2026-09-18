"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Activity } from "lucide-react";
import { api, type VariantListItem } from "@/lib/api";
import { platformApi } from "@/lib/platform/client";
import { humanError } from "@/lib/platform/errors";
import type { DriftSnapshot, ModelOODResult } from "@/lib/platform/types";
import DriftPanel from "@/components/platform/DriftPanel";
import OODPanel from "@/components/platform/OODPanel";
import { ErrorBanner, PageHeader, StatusBadge, ghostBtn, primaryBtn } from "@/components/platform/ui";

export default function ModelMonitoringPage() {
  const [snap, setSnap] = useState<DriftSnapshot | null>(null);
  const [ood, setOod] = useState<ModelOODResult | null>(null);
  const [variants, setVariants] = useState<VariantListItem[]>([]);
  const [variantId, setVariantId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    platformApi
      .monitorLatest()
      .then(setSnap)
      .catch((e) => setError(humanError(e)));
    api
      .variants()
      .then((rows) => {
        setVariants(rows);
        setVariantId(rows.find((v) => v.showcase)?.id || rows[0]?.id || "");
      })
      .catch(() => undefined);
  }, []);

  async function scoreVariant() {
    if (!variantId) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.analyze(variantId);
      const o = await platformApi.monitorOod(
        {
          probabilities: result.ml.probabilities,
          top_class: result.ml.top_class,
          model_version: result.ml.model_version,
        },
        result.acmg.classification,
      );
      setOod(o);
      const snapshot = await platformApi.monitorSnapshot([
        {
          probabilities: result.ml.probabilities,
          top_class: result.ml.top_class,
          gene: result.variant.gene,
          model_version: result.ml.model_version,
        },
      ]);
      setSnap(snapshot);
    } catch (e) {
      setError(humanError(e));
    } finally {
      setBusy(false);
    }
  }

  const empty = !snap || snap.n === 0;

  return (
    <div className="mx-auto max-w-7xl px-6 py-10 sm:px-8">
      <PageHeader
        icon={Activity}
        title="Model Monitoring"
        subtitle="How the model is behaving now — complementary to held-out Model Evaluation."
        actions={
          <Link href="/model-evaluation" className="text-sm font-semibold text-cyan">
            Open Model Evaluation →
          </Link>
        }
      />
      <ErrorBanner message={error} />
      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="card p-4">
          <p className="text-[10px] uppercase tracking-widest text-muted">Current model</p>
          <p className="mt-2 text-sm font-semibold">{ood?.model_version ?? snap?.note ?? "No snapshot yet"}</p>
        </div>
        <div className="card p-4">
          <p className="text-[10px] uppercase tracking-widest text-muted">Model version</p>
          <p className="mt-2 text-sm font-semibold">{ood?.model_version ?? "—"}</p>
        </div>
        <div className="card p-4">
          <p className="text-[10px] uppercase tracking-widest text-muted">Inference count</p>
          <p className="mt-2 text-lg font-bold">{snap?.n ?? 0}</p>
        </div>
        <div className="card p-4">
          <p className="text-[10px] uppercase tracking-widest text-muted">Average confidence</p>
          <p className="mt-2 text-lg font-bold">
            {ood?.calibrated_probability != null ? ood.calibrated_probability.toFixed(3) : "—"}
          </p>
        </div>
        <div className="card p-4">
          <p className="text-[10px] uppercase tracking-widest text-muted">OOD rate</p>
          <p className="mt-2 text-lg font-bold">{snap?.ood_rate ?? "—"}</p>
        </div>
        <div className="card p-4">
          <p className="text-[10px] uppercase tracking-widest text-muted">Drift status</p>
          <div className="mt-2">
            <StatusBadge label={snap?.drift_level ?? "LOW"} />
          </div>
        </div>
        <div className="card p-4">
          <p className="text-[10px] uppercase tracking-widest text-muted">Missing feature rate</p>
          <p className="mt-2 text-lg font-bold">{snap?.missingness ?? "—"}</p>
        </div>
      </div>
      <div className="mb-4 flex flex-wrap gap-2">
        <select
          className="rounded-lg border border-navy-950/10 px-3 py-2 text-sm"
          value={variantId}
          onChange={(e) => setVariantId(e.target.value)}
        >
          {variants.map((v) => (
            <option key={v.id} value={v.id}>
              {v.gene} {v.hgvs_c}
            </option>
          ))}
        </select>
        <button type="button" className={primaryBtn()} disabled={busy || !variantId} onClick={() => void scoreVariant()}>
          Score selected variant
        </button>
        <button
          type="button"
          className={ghostBtn()}
          disabled={busy}
          onClick={() => {
            platformApi
              .monitorLatest()
              .then(setSnap)
              .catch((e) => setError(humanError(e)));
          }}
        >
          Refresh snapshot
        </button>
      </div>
      {empty && !ood ? null : null}
      <div className="grid gap-4 lg:grid-cols-2">
        <OODPanel ood={ood} />
        <DriftPanel snap={snap} />
      </div>
    </div>
  );
}
