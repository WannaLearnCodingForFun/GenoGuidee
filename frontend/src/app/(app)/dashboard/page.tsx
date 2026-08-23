"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { CheckCircle2, Clock, FileUp, Stethoscope, UserRound } from "lucide-react";
import { api, type WorkupResult } from "@/lib/api";
import { WorkupStages, workupPayload } from "@/components/WorkupStages";
import { createClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { useAccount } from "@/lib/useAccount";

const ROLE_LABEL: Record<string, string> = {
  doctor: "Doctor",
  patient: "Patient",
  lab_technician: "Lab Technician",
};

// Plain-language mapping — patients never see raw ACMG classification codes
// (Phase B2's clinical-safety norm: patients get a status, not a bucket).
const PLAIN_STATUS: Record<string, string> = {
  pathogenic: "A significant finding was identified and is being reviewed with your care team.",
  likely_pathogenic: "A likely significant finding was identified and is being reviewed with your care team.",
  benign: "No significant finding was identified in this result.",
  likely_benign: "No significant finding was identified in this result.",
  vus: "This result needs further review before a finding can be confirmed.",
};

interface DoctorWidgetData {
  patients: { id: string; mrn: string }[];
  pendingSignoffs: number;
  recentInterpretations: { id: number; variant: string; created_at: string }[];
}

interface PatientWidgetData {
  uploads: { id: string; filename: string; status: string; uploaded_at: string }[];
  latestStatus: string | null;
  identifier?: string | null;
  linked?: boolean;
  message?: string | null;
  workup?: WorkupResult | null;
}

interface LabWidgetData {
  orders: { id: number; status: string; created_at: string }[];
}

function StatCard({ icon: Icon, label, value }: { icon: typeof Clock; label: string; value: string | number }) {
  return (
    <div className="card flex items-center gap-3 p-4">
      <span className="grid size-9 shrink-0 place-items-center rounded-lg border border-cyan/25 bg-cyan/10 text-cyan">
        <Icon className="size-4" />
      </span>
      <div>
        <p className="text-lg font-bold leading-none">{value}</p>
        <p className="mt-1 text-xs text-muted">{label}</p>
      </div>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <p className="rounded-lg border border-dashed border-navy-950/10 p-4 text-sm text-muted">{text}</p>;
}

function DoctorWidgets() {
  const [data, setData] = useState<DoctorWidgetData | null>(null);

  useEffect(() => {
    if (!isSupabaseConfigured()) {
      api.clinicalOverview()
        .then((o) => {
          setData({
            patients: o.patients.map((p) => ({
              id: String((p as { id: number }).id),
              mrn: String((p as { identifier?: string }).identifier ?? p.id),
            })),
            pendingSignoffs: o.pending_signoffs,
            recentInterpretations: [],
          });
        })
        .catch(() => setData({ patients: [], pendingSignoffs: 0, recentInterpretations: [] }));
      return;
    }
    const supabase = createClient();
    (async () => {
      const { data: userData } = await supabase.auth.getUser();
      const uid = userData.user?.id;
      if (!uid) {
        setData({ patients: [], pendingSignoffs: 0, recentInterpretations: [] });
        return;
      }

      const { data: patients } = await supabase
        .from("patients")
        .select("id, mrn")
        .eq("primary_doctor_id", uid);

      const patientIds = (patients ?? []).map((p: { id: string }) => p.id);

      let pendingSignoffs = 0;
      let recentInterpretations: DoctorWidgetData["recentInterpretations"] = [];
      if (patientIds.length > 0) {
        const { count } = await supabase
          .from("interpretations")
          .select("id", { count: "exact", head: true })
          .in("patient_id", patientIds)
          .is("reviewed_at", null);
        pendingSignoffs = count ?? 0;

        const { data: recent } = await supabase
          .from("interpretations")
          .select("id, variant, created_at")
          .in("patient_id", patientIds)
          .order("created_at", { ascending: false })
          .limit(5);
        recentInterpretations = recent ?? [];
      }

      setData({ patients: patients ?? [], pendingSignoffs, recentInterpretations });
    })();
  }, []);

  if (!data) return <EmptyState text="Loading your care team…" />;

  return (
    <div className="mt-8 space-y-6">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard icon={UserRound} label="Patients under your care" value={data.patients.length} />
        <StatCard icon={Clock} label="Pending sign-offs" value={data.pendingSignoffs} />
        <StatCard icon={Stethoscope} label="Recent interpretations" value={data.recentInterpretations.length} />
      </div>

      <div className="card p-5">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">Recent interpretations</h2>
        {data.recentInterpretations.length === 0 ? (
          <div className="mt-3">
            <EmptyState text="No interpretations recorded yet." />
          </div>
        ) : (
          <ul className="mt-3 divide-y divide-navy-950/8">
            {data.recentInterpretations.map((i) => (
              <li key={i.id} className="flex items-center justify-between py-2 text-sm">
                <span className="mono">{i.variant}</span>
                <span className="text-xs text-muted">{new Date(i.created_at).toLocaleDateString()}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card p-5">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">Your patients</h2>
        {data.patients.length === 0 ? (
          <div className="mt-3">
            <EmptyState text="No patients assigned yet." />
          </div>
        ) : (
          <ul className="mt-3 divide-y divide-navy-950/8">
            {data.patients.map((p) => (
              <li key={p.id} className="py-2 text-sm">
                {p.mrn}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function PatientWidgets() {
  const { account, loading } = useAccount();
  const [data, setData] = useState<PatientWidgetData | null>(null);

  useEffect(() => {
    if (loading || !account) return;
    if (!isSupabaseConfigured()) {
      api.patientMe()
        .then(async (me) => {
          let result = workupPayload(me.workup);
          if (!result && me.patient?.id) {
            try {
              result = workupPayload(await api.clinicalWorkupResult(me.patient.id));
            } catch {
              /* no stored workup yet */
            }
          }
          setData({
            uploads: (me.uploads ?? []).map((u) => ({
              id: String(u.id),
              filename: u.filename,
              status: u.parsing_status,
              uploaded_at: new Date(u.uploaded_at * 1000).toISOString(),
            })),
            latestStatus: result
              ? null
              : me.reconciliations?.[0]
                ? PLAIN_STATUS[me.reconciliations[0].final_classification.toLowerCase()]
                  ?? "Your care team has recorded a result for review."
                : me.linked
                  ? "Your record is stored. No reviewed result is available yet."
                  : null,
            identifier: me.patient?.identifier ?? null,
            linked: me.linked,
            message: me.message ?? null,
            workup: result,
          });
        })
        .catch(() => setData({ uploads: [], latestStatus: null, linked: false }));
      return;
    }
    const supabase = createClient();
    (async () => {
      const { data: userData } = await supabase.auth.getUser();
      const uid = userData.user?.id;
      if (!uid) {
        setData({ uploads: [], latestStatus: null });
        return;
      }

      const { data: uploads } = await supabase
        .from("vcf_uploads")
        .select("id, filename, status, uploaded_at")
        .eq("patient_id", uid)
        .order("uploaded_at", { ascending: false })
        .limit(5);

      const { data: interpretations } = await supabase
        .from("interpretations")
        .select("acmg_classification")
        .eq("patient_id", uid)
        .order("created_at", { ascending: false })
        .limit(1);

      const latestClassification = interpretations?.[0]?.acmg_classification?.toLowerCase() ?? null;
      const latestStatus = latestClassification
        ? PLAIN_STATUS[latestClassification] ?? "Your result is being reviewed with your care team."
        : null;

      setData({ uploads: uploads ?? [], latestStatus });
    })();
  }, [account, loading]);

  if (!data) return <EmptyState text="Loading your status…" />;

  return (
    <div className="mt-8 space-y-6">
      <div className="card p-5">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">Your record</h2>
        <p className="mt-2 text-sm">
          {data.linked && data.identifier ? (
            <>Patient ID: <span className="font-mono font-semibold">{data.identifier}</span></>
          ) : (
            data.message || "Your patient record exists, but your account has not been linked yet."
          )}
        </p>
      </div>
      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-muted">Your result status</h2>
        {data.workup ? (
          <WorkupStages result={data.workup} />
        ) : data.latestStatus ? (
          <div className="card p-5">
            <p className="text-sm">{data.latestStatus}</p>
          </div>
        ) : (
          <div className="card p-5">
            <EmptyState text="No results are available yet. Once your care team has completed a clinical workup, the same result cards will appear here." />
          </div>
        )}
      </div>

      <div className="card p-5">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">Your uploads</h2>
        {data.uploads.length === 0 ? (
          <div className="mt-3">
            <EmptyState text="No uploads yet." />
          </div>
        ) : (
          <ul className="mt-3 divide-y divide-navy-950/8">
            {data.uploads.map((u) => (
              <li key={u.id} className="flex items-center justify-between py-2 text-sm">
                <span className="flex items-center gap-2">
                  <FileUp className="size-3.5 text-muted" />
                  {u.filename}
                </span>
                <span className="text-xs uppercase tracking-wide text-cyan">{u.status}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function LabTechnicianWidgets() {
  const [data, setData] = useState<LabWidgetData | null>(null);

  useEffect(() => {
    if (!isSupabaseConfigured()) {
      api.clinicalOverview()
        .then((o) => {
          setData({
            orders: o.uploads.map((u) => ({
              id: Number((u as { id: number }).id),
              status: String((u as { parsing_status?: string }).parsing_status ?? ""),
              created_at: new Date(Number((u as { uploaded_at?: number }).uploaded_at ?? 0) * 1000).toISOString(),
            })),
          });
        })
        .catch(() => setData({ orders: [] }));
      return;
    }
    const supabase = createClient();
    (async () => {
      const { data: userData } = await supabase.auth.getUser();
      const uid = userData.user?.id;
      if (!uid) {
        setData({ orders: [] });
        return;
      }

      const { data: orders } = await supabase
        .from("lab_orders")
        .select("id, status, created_at")
        .eq("lab_technician_id", uid)
        .order("created_at", { ascending: false });

      setData({ orders: orders ?? [] });
    })();
  }, []);

  if (!data) return <EmptyState text="Loading your assigned orders…" />;

  const byStatus = data.orders.reduce<Record<string, number>>((acc, o) => {
    acc[o.status] = (acc[o.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="mt-8 space-y-6">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        {(["pending", "in_progress", "completed", "cancelled"] as const).map((s) => (
          <StatCard key={s} icon={CheckCircle2} label={s.replace("_", " ")} value={byStatus[s] ?? 0} />
        ))}
      </div>

      <div className="card p-5">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">Assigned lab orders</h2>
        {data.orders.length === 0 ? (
          <div className="mt-3">
            <EmptyState text="No lab orders assigned to you yet." />
          </div>
        ) : (
          <ul className="mt-3 divide-y divide-navy-950/8">
            {data.orders.map((o) => (
              <li key={o.id} className="flex items-center justify-between py-2 text-sm">
                <span>Order #{o.id}</span>
                <span className="text-xs uppercase tracking-wide text-cyan">{o.status}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function Overview() {
  const { account } = useAccount();
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    api.status().catch(() => setOffline(true));
  }, []);

  const username = account?.email?.split("@")[0] ?? account?.name ?? "there";

  return (
    <div className="relative min-h-screen overflow-hidden">
      {/* Hero background */}
      <div className="absolute inset-0 grid-texture" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_30%_20%,rgba(180,24,45,0.07),transparent_70%)]" />

      <div className="relative z-10 mx-auto max-w-6xl px-8 py-14">
        {/* Hero */}
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: "easeOut" }}
          className="flex items-start justify-between gap-4"
        >
          <div>
            <h1 className="text-5xl font-black tracking-tight">
              Welcome, <span className="text-gradient">{username}</span>
            </h1>

            {offline && (
              <p className="mt-4 text-sm text-warning">
                Backend not reachable — start it with{" "}
                <code className="mono rounded bg-navy-950/5 px-1.5 py-0.5">uvicorn app.main:app --port 8000</code>
              </p>
            )}
          </div>

          {account?.role && (
            <span className="mt-2 shrink-0 rounded-full border border-cyan/25 bg-cyan/5 px-4 py-1.5 text-xs font-semibold uppercase tracking-widest text-cyan">
              {ROLE_LABEL[account.role] ?? account.role}
            </span>
          )}
        </motion.div>

        {account?.role === "doctor" && <DoctorWidgets />}
        {account?.role === "patient" && <PatientWidgets />}
        {account?.role === "lab_technician" && <LabTechnicianWidgets />}
      </div>
    </div>
  );
}
