"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Activity, Dna, Info, TrendingUp } from "lucide-react";
import {
  api,
  type ClinicalPatient,
  type GenomicsTimeline,
  type GenomicsVariant,
} from "@/lib/api";
import { useAccount } from "@/lib/useAccount";
import { classColor } from "@/lib/ui";

const TREND_TONE: Record<string, string> = {
  IMPROVING: "text-success border-success/40 bg-success/10",
  STABLE: "text-cyan border-cyan/40 bg-cyan/10",
  WORSENING: "text-error border-error/40 bg-error/10",
  MIXED: "text-warning border-warning/40 bg-warning/10",
  UNCERTAIN: "text-muted border-navy-950/15 bg-panel2",
  INCREASING: "text-error border-error/40 bg-error/10",
  DECREASING: "text-success border-success/40 bg-success/10",
  INSUFFICIENT_DATA: "text-muted border-navy-950/15 bg-panel2",
};

type HeatMetric = "vaf" | "pathogenicity" | "risk";
type DetailTab = "vaf" | "pathogenicity" | "risk" | "acmg";
type Filter = "all" | "Pathogenic" | "Likely Pathogenic" | "VUS" | "new" | "persistent" | "reclassified";

function fmtDate(ts?: number | null) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function pct(v?: number | null) {
  if (v == null) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

export default function GenomicTimelinePage() {
  return (
    <Suspense fallback={<p className="px-8 py-8 text-sm text-muted">Loading timeline…</p>}>
      <GenomicTimelineInner />
    </Suspense>
  );
}

function GenomicTimelineInner() {
  const { account, loading } = useAccount();
  const search = useSearchParams();
  const requested = Number(search.get("patient") || "") || null;
  const [patients, setPatients] = useState<ClinicalPatient[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [data, setData] = useState<GenomicsTimeline | null>(null);
  const [therapy, setTherapy] = useState<Awaited<ReturnType<typeof api.clinicalGenomicsTherapy>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [heat, setHeat] = useState<HeatMetric>("pathogenicity");
  const [tab, setTab] = useState<DetailTab>("vaf");
  const [filter, setFilter] = useState<Filter>("all");
  const [picked, setPicked] = useState<GenomicsVariant | null>(null);
  const [openCard, setOpenCard] = useState<string | null>(null);
  const canSeed = account?.role === "doctor" || account?.role === "lab_technician";

  useEffect(() => {
    if (loading || !account) return;
    api.clinicalPatients()
      .then((rows) => {
        setPatients(rows);
        setSelectedId((prev) => requested ?? prev ?? rows[0]?.id ?? null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load patients"));
  }, [account, loading]);

  useEffect(() => {
    if (!account || selectedId == null) {
      setData(null);
      return;
    }
    setError(null);
    api.clinicalGenomicsTimeline(selectedId)
      .then((tl) => {
        setData(tl);
        setPicked(tl.variants[0] ?? null);
      })
      .catch((e) => {
        const msg = e instanceof Error ? e.message : "Unable to load timeline";
        if (msg === "Not Found" || msg.includes("404")) {
          setData(null);
          setError(null);
          return;
        }
        setError(msg);
      });
    api.clinicalGenomicsTherapy(selectedId).then(setTherapy).catch(() => setTherapy(null));
  }, [account, selectedId]);

  const chart = useMemo(
    () =>
      (data?.snapshots ?? []).map((s) => ({
        name: `Test ${s.test_number}`,
        date: fmtDate(s.test_date),
        score: s.overall_risk_score,
      })),
    [data],
  );

  const filtered = useMemo(() => {
    const rows = data?.variants ?? [];
    const cmp = data?.latest_comparison;
    const newIds = new Set((cmp?.newly_detected ?? []).map((v) => String(v.canonical_variant_id)));
    const persistIds = new Set((cmp?.persistent ?? []).map((v) => String(v.canonical_variant_id)));
    const reIds = new Set((cmp?.reclassified ?? []).map((v) => String(v.canonical_variant_id)));
    return rows.filter((v) => {
      if (filter === "all") return true;
      if (filter === "new") return newIds.has(v.canonical_variant_id);
      if (filter === "persistent") return persistIds.has(v.canonical_variant_id);
      if (filter === "reclassified") return reIds.has(v.canonical_variant_id);
      return v.current_classification === filter;
    });
  }, [data, filter]);

  async function seedDemo() {
    try {
      setError(null);
      const seeded = await api.clinicalSeedLongitudinalDemo();
      const rows = await api.clinicalPatients();
      setPatients(rows);
      const pick =
        seeded.patients?.find((p) => p.identifier === "PAT-2026-000002") ??
        seeded.patients?.[0] ??
        seeded.patient;
      setSelectedId(pick.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to seed demo");
    }
  }

  return (
    <div className="px-8 py-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.25em] text-muted">Progression</p>
          <h1 className="mt-1 flex items-center gap-2 text-2xl font-bold">
            <TrendingUp className="size-6 text-cyan" /> Genomic Timeline
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Observed tests only. Historical snapshots are not overwritten. This is not a mortality prediction.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            className="rounded-lg border border-navy-950/15 bg-panel2 px-3 py-2 text-sm"
            value={selectedId ?? ""}
            onChange={(e) => setSelectedId(e.target.value ? Number(e.target.value) : null)}
          >
            {patients.map((p) => (
              <option key={p.id} value={p.id}>
                {p.identifier} {p.full_name ? `· ${p.full_name}` : ""}
              </option>
            ))}
          </select>
          {canSeed && (
            <button type="button" className="rounded-lg border border-cyan/30 px-3 py-2 text-xs font-semibold text-cyan" onClick={seedDemo}>
              Load 4-test demo on two patients
            </button>
          )}
        </div>
      </div>

      {error && (
        <p className="mt-4 rounded-lg border border-error/30 bg-error/5 px-3 py-2 text-sm text-error">{error}</p>
      )}
      {data?.synthetic && (
        <p className="mt-4 rounded-lg border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-warning">
          Synthetic demonstration patient. Not a real clinical record.
        </p>
      )}

      {(!data || !(data.snapshots ?? []).length) ? (
        <p className="mt-6 text-sm text-muted">
          No repeated tests stored for this patient yet. Use{" "}
          <span className="font-semibold">Load 4-test demo on two patients</span> to attach
          marked synthetic snapshots (one worsening BRCA1 profile, one improving FAS profile).
        </p>
      ) : (
        <>
          <section className="card mt-6 p-5">
            <div className="flex flex-wrap items-center gap-4">
              <Stat label="Current risk" value={data.current_score ?? "—"} />
              <Stat label="Baseline" value={data.baseline_score ?? "—"} />
              <Stat label="Change" value={data.delta == null ? "—" : data.delta > 0 ? `+${data.delta}` : data.delta} />
              <span className={`rounded-full border px-3 py-1 text-xs font-bold ${TREND_TONE[data.trend] ?? TREND_TONE.UNCERTAIN}`}>
                {data.trend}
              </span>
            </div>
            <div className="mt-5 h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chart}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,23,42,0.08)" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="score" stroke="#0891b2" strokeWidth={2} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="mt-4 grid gap-3 md:grid-cols-4">
            {(data.snapshots ?? []).map((s) => (
              <button
                key={s.id}
                type="button"
                className="card p-4 text-left"
                onClick={() => api.clinicalGenomicsSnapshot(data.patient_id, s.id).then(() => undefined)}
              >
                <p className="text-[10px] uppercase tracking-widest text-muted">Test #{s.test_number}</p>
                <p className="mt-1 text-sm font-semibold">{fmtDate(s.test_date)}</p>
                <p className="mt-2 text-xs text-muted">
                  {s.variant_count} variants · P {s.pathogenic_variant_count} · VUS {s.vus_count}
                </p>
                <p className="mt-1 text-lg font-bold">{s.overall_risk_score ?? "—"}</p>
                <p className={`mt-1 inline-block rounded-full border px-2 py-0.5 text-[10px] font-bold ${TREND_TONE[s.trend ?? "UNCERTAIN"]}`}>
                  {s.trend ?? "UNCERTAIN"}
                </p>
              </button>
            ))}
          </section>

          <section className="card mt-4 p-5">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-[0.25em] text-muted">Change summary</h2>
            <p className="text-sm">{data.change_summary || "A second test is required before a comparison can be written."}</p>
          </section>

          <ComparisonCards data={data} open={openCard} setOpen={setOpenCard} />

          <section className="card mt-4 p-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-xs font-semibold uppercase tracking-[0.25em] text-muted">Variant × test heatmap</h2>
              <div className="flex gap-1">
                {(["pathogenicity", "vaf", "risk"] as HeatMetric[]).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setHeat(m)}
                    className={`rounded-full px-2.5 py-1 text-[10px] font-bold uppercase ${heat === m ? "bg-cyan/15 text-cyan" : "text-muted"}`}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </div>
            <Heatmap variants={filtered} snapshots={data.snapshots} metric={heat} onPick={setPicked} />
          </section>

          <section className="card mt-4 p-5">
            <div className="mb-3 flex flex-wrap gap-2">
              {(["all", "Pathogenic", "Likely Pathogenic", "VUS", "new", "persistent", "reclassified"] as Filter[]).map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setFilter(f)}
                  className={`rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase ${filter === f ? "border-cyan/40 text-cyan" : "border-navy-950/10 text-muted"}`}
                >
                  {f}
                </button>
              ))}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-[10px] uppercase tracking-widest text-muted">
                  <tr>
                    <th className="py-2">Gene</th>
                    <th>Variant</th>
                    <th>Class</th>
                    <th>VAF</th>
                    <th>ML P</th>
                    <th>Trend</th>
                    <th>First</th>
                    <th>Last</th>
                    <th>Tests</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((v) => (
                    <tr
                      key={v.canonical_variant_id}
                      className="cursor-pointer border-t border-navy-950/5 hover:bg-panel2/60"
                      onClick={() => setPicked(v)}
                    >
                      <td className="py-2 font-semibold">{v.gene ?? "—"}</td>
                      <td className="mono text-xs">{v.hgvs ?? v.canonical_variant_id}</td>
                      <td className={classColor(v.current_classification ?? "").text}>{v.current_classification ?? "—"}</td>
                      <td>{pct(v.current_vaf)}</td>
                      <td>{pct(v.current_pathogenicity_probability)}</td>
                      <td>{v.trend}</td>
                      <td>{fmtDate(v.first_detected)}</td>
                      <td>{fmtDate(v.last_detected)}</td>
                      <td>{v.number_of_tests_detected}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {picked && <VariantDetail variant={picked} snapshots={data.snapshots} tab={tab} setTab={setTab} />}

          <section className="card mt-4 p-5">
            <h2 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
              <Activity className="size-3.5" /> Projected risk trajectory
            </h2>
            <p className="text-xs text-muted">{data.projection.disclaimer}</p>
            <p className="mt-2 text-sm">{data.outcome.message}</p>
            {!data.projection.available ? (
              <p className="mt-3 rounded-lg bg-panel2 px-3 py-2 text-sm">
                {data.projection.message || "Projection unavailable — additional longitudinal observations required."}
              </p>
            ) : (
              <div className="mt-3 grid gap-3 md:grid-cols-3">
                {(data.projection.forecast ?? []).map((f) => (
                  <div key={f.interval} className="rounded-xl border border-navy-950/10 p-3">
                    <p className="text-[10px] uppercase text-muted">+{f.interval} interval</p>
                    <p className="text-lg font-bold">{f.score}</p>
                    <p className="text-xs text-muted">CI {f.ci_low}–{f.ci_high}</p>
                  </div>
                ))}
                <div className="rounded-xl border border-navy-950/10 p-3 text-xs text-muted">
                  Model {data.projection.model} · n={data.projection.n_observations} · confidence {data.projection.confidence}
                  {data.projection.threshold_crossing_intervals != null && (
                    <p className="mt-1">
                      Model-estimated threshold ({data.projection.risk_threshold}) crossing: approximately{" "}
                      {data.projection.threshold_crossing_intervals} future testing intervals.
                    </p>
                  )}
                </div>
              </div>
            )}
          </section>

          {therapy?.reclassification_notes?.length ? (
            <section className="card mt-4 p-5">
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-[0.25em] text-muted">Therapy relevance</h2>
              <p className="mb-2 text-xs text-muted">{therapy.disclaimer}</p>
              {therapy.reclassification_notes.map((n) => (
                <p key={n.gene} className="text-sm">
                  <span className="font-semibold">{n.gene}</span> {n.classification_path.join(" → ")}. {n.note}
                </p>
              ))}
            </section>
          ) : null}

          <p className="mt-4 flex items-start gap-2 text-xs text-muted">
            <Info className="mt-0.5 size-3.5 shrink-0" />
            {data.disclaimer} Scoring weights are documented in configs/longitudinal.yaml.
          </p>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-widest text-muted">{label}</p>
      <p className="text-2xl font-black">{value}</p>
    </div>
  );
}

function ComparisonCards({
  data,
  open,
  setOpen,
}: {
  data: GenomicsTimeline;
  open: string | null;
  setOpen: (v: string | null) => void;
}) {
  const cmp = data.latest_comparison;
  if (!cmp) return null;
  const cards = [
    ["new", "New variants", cmp.newly_detected],
    ["persist", "Persistent", cmp.persistent],
    ["reclass", "Reclassified", cmp.reclassified],
    ["gone", "Not detected in current sample", cmp.not_detected_in_current_sample],
  ] as const;
  return (
    <section className="mt-4 grid gap-3 md:grid-cols-4">
      {cards.map(([key, label, items]) => (
        <button key={key} type="button" className="card p-4 text-left" onClick={() => setOpen(open === key ? null : key)}>
          <p className="text-[10px] uppercase tracking-widest text-muted">{label}</p>
          <p className="mt-1 text-2xl font-black">{items.length}</p>
          {open === key && (
            <ul className="mt-2 space-y-1 text-xs text-muted">
              {items.slice(0, 8).map((item, i) => (
                <li key={i}>
                  {String(item.gene ?? item.canonical_variant_id ?? "variant")}
                  {item.from ? ` ${item.from}→${item.to}` : ""}
                </li>
              ))}
            </ul>
          )}
        </button>
      ))}
      <p className="md:col-span-4 text-xs text-muted">{cmp.not_detected_note}</p>
    </section>
  );
}

function Heatmap({
  variants,
  snapshots,
  metric,
  onPick,
}: {
  variants: GenomicsVariant[];
  snapshots: GenomicsTimeline["snapshots"];
  metric: HeatMetric;
  onPick: (v: GenomicsVariant) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr>
            <th className="py-1 text-left text-muted">Variant</th>
            {snapshots.map((s) => (
              <th key={s.id} className="px-2 text-muted">T{s.test_number}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {variants.slice(0, 24).map((v) => (
            <tr key={v.canonical_variant_id}>
              <td className="cursor-pointer py-1 font-semibold" onClick={() => onPick(v)}>
                {v.gene ?? "—"} {v.hgvs ?? ""}
              </td>
              {snapshots.map((s) => {
                const pt = (v.points ?? []).find((p) => Number(p.snapshot_id) === s.id);
                const detected = pt && pt.detected !== false && pt.detected !== 0;
                let intensity = 0;
                if (detected) {
                  if (metric === "vaf") intensity = Number(pt.allele_frequency ?? pt.allele_fraction ?? 0);
                  else if (metric === "pathogenicity") intensity = Number(pt.pathogenicity_probability ?? 0);
                  else intensity = Number(pt.trajectory_score ?? 0) / 100;
                }
                return (
                  <td key={s.id} className="px-2">
                    <span
                      className="inline-block size-4 rounded-full"
                      style={{
                        background: detected ? `rgba(8,145,178,${0.2 + intensity * 0.8})` : "transparent",
                        border: detected ? "none" : "1px dashed rgba(15,23,42,0.2)",
                      }}
                      title={detected ? `${metric} ${intensity.toFixed(2)}` : "not detected"}
                    />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function VariantDetail({
  variant,
  snapshots,
  tab,
  setTab,
}: {
  variant: GenomicsVariant;
  snapshots: GenomicsTimeline["snapshots"];
  tab: DetailTab;
  setTab: (t: DetailTab) => void;
}) {
  const series = snapshots.map((s) => {
    const pt = (variant.points ?? []).find((p) => Number(p.snapshot_id) === s.id);
    return {
      date: fmtDate(s.test_date),
      vaf: pt ? Number(pt.allele_frequency ?? pt.allele_fraction ?? 0) * 100 : null,
      pathogenicity: pt ? Number(pt.pathogenicity_probability ?? 0) * 100 : null,
      risk: pt ? Number(pt.trajectory_score ?? 0) : null,
      acmg: pt?.acmg_classification ?? null,
    };
  });
  const key = tab === "acmg" ? "pathogenicity" : tab;
  return (
    <section className="card mt-4 p-5">
      <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
        <Dna className="size-3.5" /> {variant.gene} {variant.hgvs}
      </h2>
      <p className="mt-1 text-xs text-muted">
        Score {variant.variant_trajectory_score ?? "—"} · components{" "}
        {variant.components
          ? Object.entries(variant.components).map(([k, v]) => `${k} ${v}`).join(" · ")
          : "—"}
      </p>
      <p className="mt-2 text-xs text-muted">
        ML prediction is a calibrated model probability. ACMG classification is authoritative and is not overridden by ML.
      </p>
      <div className="mt-3 flex gap-2">
        {(["vaf", "pathogenicity", "risk", "acmg"] as DetailTab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`rounded-full px-2.5 py-1 text-[10px] font-bold uppercase ${tab === t ? "bg-cyan/15 text-cyan" : "text-muted"}`}
          >
            {t}
          </button>
        ))}
      </div>
      {tab === "acmg" ? (
        <p className="mt-4 text-sm">{(variant.classification_history ?? []).filter(Boolean).join(" → ") || "No ACMG history yet."}</p>
      ) : (
        <div className="mt-4 h-52">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={series}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,23,42,0.08)" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Line type="monotone" dataKey={key} stroke="#7c3aed" strokeWidth={2} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
