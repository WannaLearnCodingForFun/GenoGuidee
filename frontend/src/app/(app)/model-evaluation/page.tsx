"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { BarChart3, Info } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAccount } from "@/lib/useAccount";

export default function ModelEvaluationPage() {
  const { account, loading } = useAccount();
  const [payload, setPayload] = useState<Awaited<ReturnType<typeof api.clinicalModelEvaluation>> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading || !account) return;
    if (account.role === "patient") {
      setError("Model evaluation is limited to clinicians and laboratory staff.");
      return;
    }
    api.clinicalModelEvaluation()
      .then(setPayload)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load model registry"));
  }, [account, loading]);

  const ablations = (payload?.ablations ?? []).map((row) => ({
    name: String(row.name ?? "").replace(/_/g, " "),
    "Balanced acc": Number(((row.balanced_accuracy ?? 0) * 100).toFixed(1)),
    "Macro F1": Number(((row.macro_f1 ?? 0) * 100).toFixed(1)),
    "PR-AUC": Number(((row.macro_auprc ?? 0) * 100).toFixed(1)),
  }));

  const headline = payload?.headline;
  const compare = headline
    ? [
        {
          name: "5-class UI",
          Accuracy: Number(headline.five_class.accuracy ?? 0) * 100,
        },
        {
          name: "HQ binary",
          Accuracy: Number(headline.binary_hq.accuracy ?? 0) * 100,
        },
      ]
    : [];

  return (
    <div className="px-8 py-8">
      <p className="text-[10px] font-semibold uppercase tracking-[0.25em] text-muted">Internal</p>
      <h1 className="mt-1 flex items-center gap-2 text-2xl font-bold">
        <BarChart3 className="size-6 text-cyan" /> Model evaluation
      </h1>
      <p className="mt-2 max-w-2xl text-sm text-muted">
        Held-out metrics from registered artifacts. Numbers are not edited for display.
        The five-class Variant Lab model and the high-review binary model are different tasks.
      </p>
      <Link href="/model-monitoring" className="mt-3 inline-block text-sm font-semibold text-cyan">
        Open Model Monitoring →
      </Link>
      {error && (
        <p className="mt-4 rounded-lg border border-error/30 bg-error/5 px-3 py-2 text-sm text-error">{error}</p>
      )}
      {payload && (
        <>
          <p className="mt-4 flex items-start gap-2 text-xs text-muted">
            <Info className="mt-0.5 size-3.5 shrink-0" />
            {payload.note} Leakage policy: {payload.leakage_policy}
          </p>

          {compare.length > 0 && (
            <section className="card mt-6 p-5">
              <h2 className="text-sm font-semibold">Task comparison (held-out)</h2>
              <p className="mt-1 text-xs text-muted">
                Binary HQ is stronger because VUS/conflicting labels are excluded. That is not
                the same as claiming the 5-class UI model is 85% accurate.
              </p>
              <div className="mt-4 h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={compare}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,23,42,0.08)" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="Accuracy" fill="#0891b2" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-2 text-sm">
                <div className="rounded-xl border border-navy-950/10 p-3">
                  <p className="text-[10px] uppercase text-muted">HQ binary TEST</p>
                  <p className="text-lg font-bold">{Number(headline?.binary_hq.accuracy).toFixed(4)}</p>
                  <p className="text-xs text-muted">
                    bal acc {Number(headline?.binary_hq.balanced_accuracy).toFixed(4)} · n={String(headline?.binary_hq.n)}
                  </p>
                </div>
                <div className="rounded-xl border border-navy-950/10 p-3">
                  <p className="text-[10px] uppercase text-muted">5-class UI model</p>
                  <p className="text-lg font-bold">~{Number(headline?.five_class.accuracy).toFixed(2)}</p>
                  <p className="text-xs text-muted">{String(headline?.five_class.note)}</p>
                </div>
              </div>
            </section>
          )}

          {ablations.length > 0 && (
            <section className="card mt-4 p-5">
              <h2 className="text-sm font-semibold">Feature-set ablations (capped sweep)</h2>
              <p className="mt-1 text-xs text-muted">
                Higher is better. These are real gene-disjoint numbers from research/reports/extended_eval.json.
              </p>
              <div className="mt-4 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={ablations}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,23,42,0.08)" />
                    <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-15} height={60} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="Balanced acc" fill="#0891b2" />
                    <Bar dataKey="Macro F1" fill="#7c3aed" />
                    <Bar dataKey="PR-AUC" fill="#b4182d" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>
          )}

          <div className="mt-6 grid gap-4">
            {payload.items.map((item) => {
              const metrics = (item.metrics_gene_disjoint_test || item.metrics || {}) as Record<string, unknown>;
              const leakage = (item.leakage || {}) as Record<string, unknown>;
              const training = (item.training_dataset || {}) as Record<string, unknown>;
              return (
                <section key={String(item.model_id)} className="card p-5">
                  <h2 className="text-lg font-bold">{String(item.model_id)}</h2>
                  <p className="text-xs text-muted">
                    Registered {String(item.registered ?? "—")} · split {String(item.split ?? "—")} · artifact {String(item.artifact ?? "—")}
                  </p>
                  <dl className="mt-4 grid gap-2 sm:grid-cols-3 text-sm">
                    {[
                      ["Accuracy", metrics.accuracy],
                      ["Balanced accuracy", metrics.balanced_accuracy],
                      ["Precision", metrics.precision],
                      ["Recall", metrics.recall],
                      ["F1", metrics.f1],
                      ["ROC-AUC", metrics.roc_auc],
                      ["PR-AUC", metrics.pr_auc],
                      ["n test", metrics.n],
                      ["Threshold", item.threshold],
                    ].map((row) => {
                      const k = String(row[0]);
                      const raw = row[1];
                      const display = raw == null ? "—" : typeof raw === "number" ? raw.toFixed(4) : String(raw);
                      return (
                      <div key={k}>
                        <dt className="text-[10px] uppercase tracking-widest text-muted">{k}</dt>
                        <dd className="mono font-semibold">{display}</dd>
                      </div>
                      );
                    })}
                  </dl>
                  {Array.isArray(metrics.confusion_matrix) && (
                    <p className="mt-3 text-xs text-muted">
                      Confusion [[TN, FP], [FN, TP]]: {JSON.stringify(metrics.confusion_matrix)}
                    </p>
                  )}
                  <p className="mt-2 text-xs text-muted">
                    Dataset {String(training.path ?? "—")} · leakage {String(leakage.severity ?? "—")}
                    {leakage.exact_coordinate_overlap != null ? ` · coordinate overlap ${String(leakage.exact_coordinate_overlap)}` : ""}
                  </p>
                </section>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
