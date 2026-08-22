"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  Clock,
  Download,
  FileUp,
  FlaskConical,
  History,
  Loader2,
  Trash2,
  Upload as UploadIcon,
  UserRound,
  XCircle,
} from "lucide-react";
import {
  deleteUpload,
  downloadUrl,
  getCurrentAccount,
  ingestVcf,
  listAssignablePatients,
  listUploadVariants,
  listUploads,
  type CurrentAccount,
  type PatientOption,
  type UploadProgress,
  type UploadedVariantRow,
  type VcfUpload,
} from "@/lib/uploads";
import { variantLabel, type ParseResult } from "@/lib/vcf";

const STATUS_STYLE: Record<string, { label: string; cls: string; icon: typeof CheckCircle2 }> = {
  uploading: { label: "UPLOADING", cls: "text-warning border-warning/40 bg-warning/10", icon: Loader2 },
  parsing: { label: "PARSING", cls: "text-warning border-warning/40 bg-warning/10", icon: Loader2 },
  completed: { label: "COMPLETED", cls: "text-success border-success/40 bg-success/10", icon: CheckCircle2 },
  failed: { label: "FAILED", cls: "text-error border-error/40 bg-error/10", icon: XCircle },
};

function when(iso: string): string {
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60000);
  const rel =
    mins < 1 ? "just now" : mins < 60 ? `${mins}m ago` : mins < 1440 ? `${Math.floor(mins / 60)}h ago` : `${Math.floor(mins / 1440)}d ago`;
  return `${d.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })} · ${rel}`;
}

function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}

export default function UploadPage() {
  const [account, setAccount] = useState<CurrentAccount | null>(null);
  const [patients, setPatients] = useState<PatientOption[]>([]);
  const [uploads, setUploads] = useState<VcfUpload[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const [patientId, setPatientId] = useState<string>("");
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [result, setResult] = useState<ParseResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      setUploads(await listUploads());
      setListError(null);
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Could not load uploads.");
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    getCurrentAccount().then((acc) => {
      setAccount(acc);
      // A patient's file is always about themselves — preselect and lock it.
      if (acc?.role === "patient") setPatientId(acc.id);
    });
    listAssignablePatients().then(setPatients);
    refresh();
  }, [refresh]);

  function choose(f: File | null) {
    setFile(f);
    setResult(null);
    setError(null);
    setProgress(null);
  }

  async function submit() {
    if (!file) return;
    setError(null);
    setResult(null);
    try {
      const outcome = await ingestVcf(file, patientId || null, setProgress);
      setResult(outcome.parse);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed.");
      setProgress(null);
      await refresh();
    }
  }

  const busy = progress !== null && progress.step !== "done";
  const isPatient = account?.role === "patient";

  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="absolute inset-0 grid-texture" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_30%_0%,rgba(180,24,45,0.06),transparent_70%)]" />

      <div className="relative z-10 mx-auto max-w-6xl px-8 py-12">
        <header className="mb-8">
          <h1 className="flex items-center gap-3 text-2xl font-bold tracking-tight">
            <FileUp className="size-6 text-cyan" />
            Upload &amp; Tracker
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-muted">
            Upload a patient VCF to run it through the same ESM-2 &rarr; XGBoost &rarr; ACMG pipeline
            the curated cases use. Every upload is recorded below with who uploaded it and when.
          </p>
        </header>

        {/* ---------------------------------------------------------------- */}
        {/* Upload panel                                                      */}
        {/* ---------------------------------------------------------------- */}
        <section className="card card-glow-cyan p-6">
          <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
            <UploadIcon className="size-3.5" /> New upload
          </h2>

          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              const f = e.dataTransfer.files?.[0];
              if (f) choose(f);
            }}
            onClick={() => !busy && inputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors ${
              dragging
                ? "border-cyan/60 bg-cyan/5"
                : "border-navy-950/15 hover:border-cyan/40 hover:bg-cyan/[0.03]"
            } ${busy ? "pointer-events-none opacity-60" : ""}`}
          >
            <span className="grid size-12 place-items-center rounded-xl border border-cyan/30 bg-cyan/10">
              <FileUp className="size-6 text-cyan" />
            </span>
            {file ? (
              <>
                <p className="text-sm font-semibold">{file.name}</p>
                <p className="text-xs text-muted">{bytes(file.size)} · click to choose a different file</p>
              </>
            ) : (
              <>
                <p className="text-sm font-semibold">Drop a VCF file here, or click to browse</p>
                <p className="text-xs text-muted">
                  .vcf / .txt · up to 50 MB · VEP (CSQ), SnpEff (ANN) and plain INFO annotations supported
                </p>
              </>
            )}
            <input
              ref={inputRef}
              type="file"
              accept=".vcf,.txt,text/plain"
              className="hidden"
              onChange={(e) => choose(e.target.files?.[0] ?? null)}
            />
          </div>

          <div className="mt-5 flex flex-wrap items-end gap-4">
            <div className="min-w-[260px] flex-1">
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-muted">
                Assign to patient
              </label>
              <select
                value={patientId}
                onChange={(e) => setPatientId(e.target.value)}
                disabled={busy || isPatient}
                className="w-full rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-cyan/50 disabled:opacity-60"
              >
                <option value="">Unassigned</option>
                {patients.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.full_name} · {p.mrn}
                  </option>
                ))}
              </select>
              <p className="mt-1.5 text-[11px] text-muted">
                {isPatient
                  ? "Your uploads are always filed under your own record."
                  : patients.length
                    ? "You can only file uploads against patients you are authorized for."
                    : "No patients are linked to your account yet — the upload will be unassigned."}
              </p>
            </div>

            <button
              onClick={submit}
              disabled={!file || busy}
              className="group flex items-center gap-2 rounded-xl border border-cyan/40 bg-cyan/10 px-6 py-3 text-sm font-semibold text-cyan transition-all hover:bg-cyan/20 hover:shadow-[0_0_32px_-8px_#b4182d] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? <Loader2 className="size-4 animate-spin" /> : <UploadIcon className="size-4" />}
              {busy ? "Processing…" : "Upload & parse"}
              {!busy && <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />}
            </button>
          </div>

          {progress && (
            <div className="mt-5">
              <div className="mb-2 flex items-center justify-between text-xs">
                <span className="text-muted">{progress.message}</span>
                <span className="mono text-cyan">{progress.percent}%</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-navy-950/10">
                <motion.div
                  className="h-full rounded-full bg-cyan"
                  animate={{ width: `${progress.percent}%` }}
                  transition={{ duration: 0.3 }}
                />
              </div>
            </div>
          )}

          {error && (
            <div className="mt-5 flex items-start gap-2 rounded-lg border border-error/40 bg-error/10 px-4 py-3 text-sm text-error">
              <XCircle className="mt-0.5 size-4 shrink-0" />
              {error}
            </div>
          )}

          {result && <ParseSummary result={result} />}
        </section>

        {/* ---------------------------------------------------------------- */}
        {/* Tracker                                                           */}
        {/* ---------------------------------------------------------------- */}
        <section className="mt-8">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
              <History className="size-3.5" /> Upload tracker
            </h2>
            <span className="text-xs text-muted">
              {uploads.length} upload{uploads.length === 1 ? "" : "s"} visible to you
            </span>
          </div>

          {listError && (
            <div className="card border-warning/40 p-5 text-sm text-warning">
              {listError}
              <p className="mt-2 text-xs text-muted">
                If this mentions a missing table, the upload migration has not been applied to your
                Supabase project yet.
              </p>
            </div>
          )}

          {loadingList && !listError && (
            <div className="card flex items-center gap-3 p-6 text-sm text-muted">
              <Loader2 className="size-4 animate-spin" /> Loading upload history…
            </div>
          )}

          {!loadingList && !listError && uploads.length === 0 && (
            <div className="card flex flex-col items-center gap-2 p-10 text-center">
              <Clock className="size-6 text-muted/50" />
              <p className="text-sm font-medium">No uploads yet</p>
              <p className="text-xs text-muted">
                Your first VCF upload will appear here with its timestamp and parse results.
              </p>
            </div>
          )}

          <div className="space-y-3">
            {uploads.map((u, i) => (
              <TrackerRow
                key={u.id}
                upload={u}
                index={i}
                patients={patients}
                isOwner={account?.id === u.uploader_id}
                onDeleted={refresh}
              />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------------ */

function ParseSummary({ result }: { result: ParseResult }) {
  const pct = result.variants.length
    ? Math.round((result.annotatedCount / result.variants.length) * 100)
    : 0;
  const level = pct >= 80 ? "success" : pct >= 40 ? "warning" : "error";

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={`mt-5 rounded-xl border p-5 ${
        level === "success"
          ? "border-success/40 bg-success/5"
          : level === "warning"
            ? "border-warning/40 bg-warning/5"
            : "border-error/40 bg-error/5"
      }`}
    >
      <div className="flex items-center gap-2 text-sm font-semibold">
        <CheckCircle2 className="size-4 text-success" />
        Parsed {result.variants.length.toLocaleString()} variant
        {result.variants.length === 1 ? "" : "s"}
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-4">
        {[
          { label: "Records read", value: result.totalRecords.toLocaleString() },
          { label: "Annotation source", value: result.annotationSource },
          { label: "Reference", value: result.referenceGenome ?? "not declared" },
          { label: "With in-silico scores", value: `${pct}%` },
        ].map((s) => (
          <div key={s.label}>
            <p className="text-[10px] uppercase tracking-widest text-muted">{s.label}</p>
            <p className="mt-0.5 text-sm font-semibold">{s.value}</p>
          </div>
        ))}
      </div>

      {pct < 80 && (
        <p className="mt-4 flex items-start gap-2 text-xs text-muted">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" />
          {pct === 0 ? (
            <span>
              No CADD / REVEL / SpliceAI / phyloP scores were found. ACMG will run on consequence and
              allele frequency alone, so most variants will land on VUS. Re-annotate with VEP for a
              stronger call.
            </span>
          ) : (
            <span>
              Only {pct}% of variants carry in-silico scores. Unannotated variants will lean toward
              VUS because PP3/BP4 cannot be evaluated for them.
            </span>
          )}
        </p>
      )}

      {result.truncated && (
        <p className="mt-3 flex items-start gap-2 text-xs text-warning">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          File exceeded the 5,000-variant demo cap — only the first 5,000 were stored.
        </p>
      )}

      {result.skipped > 0 && (
        <p className="mt-3 text-xs text-muted">
          {result.skipped} malformed line{result.skipped === 1 ? "" : "s"} skipped
          {result.errors.length ? `: ${result.errors[0]}` : "."}
        </p>
      )}

      <Link
        href="/variant-lab?source=uploads"
        className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-cyan hover:underline"
      >
        <FlaskConical className="size-4" />
        Analyze these variants in Variant Lab
        <ArrowRight className="size-3.5" />
      </Link>
    </motion.div>
  );
}

/* ------------------------------------------------------------------------ */

function TrackerRow({
  upload,
  index,
  patients,
  isOwner,
  onDeleted,
}: {
  upload: VcfUpload;
  index: number;
  patients: PatientOption[];
  isOwner: boolean;
  onDeleted: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [variants, setVariants] = useState<UploadedVariantRow[] | null>(null);
  const [busy, setBusy] = useState(false);

  const style = STATUS_STYLE[upload.status] ?? STATUS_STYLE.failed;
  const StatusIcon = style.icon;
  const patient = patients.find((p) => p.id === upload.patient_id);
  const spinning = upload.status === "uploading" || upload.status === "parsing";

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && variants === null) {
      setVariants(await listUploadVariants(upload.id));
    }
  }

  async function remove() {
    if (!confirm(`Delete "${upload.filename}" and its ${upload.variant_count} parsed variants?`)) return;
    setBusy(true);
    try {
      await deleteUpload(upload.id, upload.storage_path);
      onDeleted();
    } finally {
      setBusy(false);
    }
  }

  async function download() {
    const url = await downloadUrl(upload.storage_path);
    if (url) window.open(url, "_blank");
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index * 0.04, 0.3) }}
      className="card overflow-hidden"
    >
      <div className="flex flex-wrap items-center gap-4 p-4">
        <button onClick={toggle} className="flex min-w-0 flex-1 items-center gap-3 text-left">
          <ChevronDown
            className={`size-4 shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`}
          />
          <span className="grid size-9 shrink-0 place-items-center rounded-lg border border-navy-950/10 bg-panel2">
            <FileUp className="size-4 text-cyan" />
          </span>
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold">{upload.filename}</span>
            <span className="mono block truncate text-[11px] text-muted">
              {when(upload.uploaded_at)} · {bytes(upload.file_size)}
              {upload.reference_genome ? ` · ${upload.reference_genome}` : ""}
            </span>
          </span>
        </button>

        <div className="flex items-center gap-2 text-xs text-muted">
          <UserRound className="size-3.5" />
          {patient ? `${patient.full_name} · ${patient.mrn}` : upload.patient_id ? "Assigned" : "Unassigned"}
        </div>

        <div className="text-right">
          <p className="text-sm font-bold tabular-nums">{upload.variant_count.toLocaleString()}</p>
          <p className="text-[10px] uppercase tracking-widest text-muted">variants</p>
        </div>

        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-widest ${style.cls}`}
        >
          <StatusIcon className={`size-3 ${spinning ? "animate-spin" : ""}`} />
          {style.label}
        </span>

        <div className="flex items-center gap-1">
          <button
            onClick={download}
            title="Download original file"
            className="grid size-8 place-items-center rounded-lg border border-navy-950/10 text-muted transition-colors hover:border-cyan/40 hover:text-cyan"
          >
            <Download className="size-3.5" />
          </button>
          {isOwner && (
            <button
              onClick={remove}
              disabled={busy}
              title="Delete upload"
              className="grid size-8 place-items-center rounded-lg border border-navy-950/10 text-muted transition-colors hover:border-error/40 hover:text-error disabled:opacity-50"
            >
              {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Trash2 className="size-3.5" />}
            </button>
          )}
        </div>
      </div>

      {upload.status === "failed" && upload.error_message && (
        <p className="border-t border-error/20 bg-error/5 px-4 py-2.5 text-xs text-error">
          {upload.error_message}
        </p>
      )}

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden border-t border-navy-950/8"
          >
            <div className="p-4">
              {variants === null ? (
                <p className="flex items-center gap-2 text-xs text-muted">
                  <Loader2 className="size-3.5 animate-spin" /> Loading variants…
                </p>
              ) : variants.length === 0 ? (
                <p className="text-xs text-muted">No variants stored for this upload.</p>
              ) : (
                <>
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[720px] text-left text-xs">
                      <thead className="text-[10px] uppercase tracking-widest text-muted">
                        <tr className="border-b border-navy-950/8">
                          <th className="pb-2 pr-3 font-semibold">Variant</th>
                          <th className="pb-2 pr-3 font-semibold">Consequence</th>
                          <th className="pb-2 pr-3 font-semibold">gnomAD AF</th>
                          <th className="pb-2 pr-3 font-semibold">CADD</th>
                          <th className="pb-2 pr-3 font-semibold">REVEL</th>
                          <th className="pb-2 pr-3 font-semibold">SpliceAI</th>
                          <th className="pb-2 font-semibold"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {variants.slice(0, 25).map((v) => (
                          <tr key={v.id} className="border-b border-navy-950/5 last:border-0">
                            <td className="py-2 pr-3">
                              <span className="font-semibold">{variantLabel(v)}</span>
                              <span className="mono ml-2 text-[10px] text-muted">
                                {v.chrom}:{v.pos} {v.ref}&gt;{v.alt}
                              </span>
                            </td>
                            <td className="py-2 pr-3 text-muted">{v.consequence ?? "—"}</td>
                            <td className="mono py-2 pr-3 text-muted">
                              {v.gnomad_af === null ? "—" : v.gnomad_af.toExponential(1)}
                            </td>
                            <td className="mono py-2 pr-3 text-muted">{v.cadd ?? "—"}</td>
                            <td className="mono py-2 pr-3 text-muted">{v.revel ?? "—"}</td>
                            <td className="mono py-2 pr-3 text-muted">{v.spliceai ?? "—"}</td>
                            <td className="py-2">
                              <Link
                                href={`/variant-lab?source=uploads&variant=${v.id}`}
                                className="inline-flex items-center gap-1 whitespace-nowrap font-semibold text-cyan hover:underline"
                              >
                                Analyze <ArrowRight className="size-3" />
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {variants.length > 25 && (
                    <p className="mt-3 text-xs text-muted">
                      Showing 25 of {variants.length.toLocaleString()} variants.{" "}
                      <Link href="/variant-lab?source=uploads" className="text-cyan hover:underline">
                        Open Variant Lab
                      </Link>{" "}
                      to browse them all.
                    </p>
                  )}
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
