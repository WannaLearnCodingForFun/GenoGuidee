"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  BadgeCheck,
  Blocks,
  CheckCircle2,
  FileSignature,
  History,
  Link2,
  Loader2,
  ScrollText,
  ShieldCheck,
  ShieldX,
  X,
} from "lucide-react";
import { api, type LedgerBlock, type VerifyResult } from "@/lib/api";
import { shortHash, timestampLabel } from "@/lib/ui";

export default function Provenance() {
  const [blocks, setBlocks] = useState<LedgerBlock[]>([]);
  const [functions, setFunctions] = useState<string[]>([]);
  const [selected, setSelected] = useState<LedgerBlock | null>(null);
  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [auditFilter, setAuditFilter] = useState<string | null>(null);
  const [showAudit, setShowAudit] = useState(false);
  const [consent, setConsent] = useState<{ patient_id: string; state: string; record: LedgerBlock | null } | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    api
      .audit()
      .then((d) => {
        setBlocks(d.blocks);
        setFunctions(d.contract_functions);
        setSelected((prev) => {
          if (prev) return d.blocks.find((b) => b.tx_id === prev.tx_id) ?? prev;
          return (
            [...d.blocks].reverse().find((b) => b.function === "recordInterpretation") ??
            d.blocks[d.blocks.length - 1] ??
            null
          );
        });
      })
      .catch(() => setError(true));
  }, []);

  useEffect(load, [load]);

  const interpretations = useMemo(
    () => blocks.filter((b) => b.function === "recordInterpretation").length,
    [blocks],
  );

  async function runVerify() {
    if (!selected) return;
    setVerifying(true);
    setVerify(null);
    try {
      const res = await api.verify(selected.tx_id);
      // Small theatrical delay so the chain check reads as a real recomputation
      await new Promise((r) => setTimeout(r, 700));
      setVerify(res);
    } catch {
      setError(true);
    } finally {
      setVerifying(false);
    }
  }

  async function openConsent() {
    if (!selected) return;
    const pid = selected.subject_id === "UNASSIGNED" ? "G-1027" : selected.subject_id;
    const c = await api.consent(pid);
    setConsent(c);
  }

  async function toggleConsent() {
    if (!consent) return;
    if (consent.state === "GRANTED") await api.revokeConsent(consent.patient_id);
    else await api.recordConsent(consent.patient_id);
    const c = await api.consent(consent.patient_id);
    setConsent(c);
    load();
  }

  const payload = selected?.payload as Record<string, string> | undefined;

  return (
    <div className="mx-auto max-w-7xl px-8 py-10">
      <header className="mb-6">
        <h1 className="flex items-center gap-3 text-2xl font-bold tracking-tight">
          <ShieldCheck className="size-6 text-cyan" />
          Provenance Ledger
        </h1>
        <p className="mt-1 text-sm text-muted">
          Hash-chained, smart-contract-compatible local ledger. Only hashes, consent state,
          versions and timestamps are stored — genomic data never touches the chain.
        </p>
      </header>

      {error && <p className="mb-4 text-sm text-error">Backend not reachable.</p>}

      {/* Contract + stats strip */}
      <section className="card card-glow-violet mb-6 flex flex-wrap items-center gap-x-10 gap-y-4 p-5">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted">Contracts</p>
          <p className="mono mt-1 text-sm font-semibold text-violet">
            ConsentContract · InterpretationContract
          </p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted">
            Chaincode functions
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {functions.map((f) => (
              <span key={f} className="mono rounded border border-violet/25 bg-violet/5 px-2 py-0.5 text-[10px] text-violet">
                {f}
              </span>
            ))}
          </div>
        </div>
        <div className="ml-auto flex gap-8 text-center">
          <div>
            <p className="text-2xl font-black tabular-nums text-cyan">{blocks.length}</p>
            <p className="text-[10px] uppercase tracking-widest text-muted">Blocks</p>
          </div>
          <div>
            <p className="text-2xl font-black tabular-nums text-success">{interpretations}</p>
            <p className="text-[10px] uppercase tracking-widest text-muted">Interpretations</p>
          </div>
        </div>
      </section>

      {/* Chain visualization */}
      <section className="card mb-6 p-5">
        <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
          <Blocks className="size-4 text-cyan" /> Ledger chain — genesis → head
        </h2>
        <div className="flex items-center gap-1 overflow-x-auto pb-3">
          {blocks.map((b, i) => {
            const active = selected?.tx_id === b.tx_id;
            const isInterp = b.function === "recordInterpretation";
            return (
              <div key={b.tx_id} className="flex shrink-0 items-center">
                <motion.button
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(i * 0.05, 0.6) }}
                  onClick={() => {
                    setSelected(b);
                    setVerify(null);
                  }}
                  className={`w-40 rounded-xl border p-3 text-left transition-all ${
                    active
                      ? "border-cyan/60 bg-cyan/10 shadow-[0_0_20px_-6px_#b4182d]"
                      : "border-navy-950/10 bg-panel2/70 hover:border-navy-950/30"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="mono text-[10px] text-muted">#{b.block_index}</span>
                    {isInterp ? (
                      <FileSignature className="size-3.5 text-cyan" />
                    ) : (
                      <ScrollText className="size-3.5 text-violet" />
                    )}
                  </div>
                  <p className="mono mt-1 truncate text-[10px] font-semibold text-fg">
                    {b.function}
                  </p>
                  <p className="mono mt-0.5 truncate text-[9px] text-muted">{b.subject_id}</p>
                  <p className="mono mt-1 truncate text-[8px] text-cyan/70">
                    {b.block_hash.slice(0, 18)}…
                  </p>
                </motion.button>
                {i < blocks.length - 1 && <Link2 className="mx-1 size-3.5 shrink-0 text-cyan/40" />}
              </div>
            );
          })}
        </div>
      </section>

      {/* Record detail + verification */}
      {selected && payload && (
        <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
          <section className="card card-glow-cyan p-6">
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-[0.25em] text-muted">
                Record detail — block #{selected.block_index}
              </h2>
              <span
                className={`flex items-center gap-1.5 rounded-lg border px-3 py-1 text-xs font-black tracking-widest ${
                  verify
                    ? verify.verified
                      ? "border-success/50 bg-success/10 text-success"
                      : "border-error/50 bg-error/10 text-error"
                    : "border-navy-950/15 bg-navy-950/5 text-muted"
                }`}
              >
                {verify ? (
                  verify.verified ? (
                    <>
                      <BadgeCheck className="size-3.5" /> VERIFIED
                    </>
                  ) : (
                    <>
                      <ShieldX className="size-3.5" /> TAMPERED
                    </>
                  )
                ) : (
                  "UNVERIFIED"
                )}
              </span>
            </div>

            <dl className="grid grid-cols-1 gap-x-8 gap-y-3 text-sm md:grid-cols-2">
              <Row label="Patient ID" value={selected.subject_id} />
              <Row label="Contract" value={selected.contract} accent />
              <Row label="Function" value={`${selected.function}()`} mono />
              <Row label="Timestamp" value={timestampLabel(selected.timestamp)} />
              <Row label="Patient Hash" value={payload.patient_hash ? `SHA256(${shortHash(payload.patient_hash, 14)})` : "—"} mono full />
              {payload.consent_hash && (
                <Row label="Consent Hash" value={`SHA256(${shortHash(payload.consent_hash, 14)})`} mono full />
              )}
              {payload.interpretation_hash && (
                <Row label="Interpretation Hash" value={`SHA256(${shortHash(payload.interpretation_hash, 14)})`} mono full />
              )}
              {payload.variant_ref && <Row label="Interpretation" value={`${payload.variant_ref} — ${payload.classification}`} accent />}
              {payload.reconciliation_status && (
                <Row label="Reconciliation" value={payload.reconciliation_status} />
              )}
              {payload.state && <Row label="Consent state" value={payload.state} accent />}
              {payload.model_version && <Row label="Model Version" value={payload.model_version} mono />}
              {payload.evidence_version && <Row label="Evidence Version" value={payload.evidence_version} mono />}
              <Row label="Transaction ID" value={selected.tx_id} mono full />
              <Row label="Block Hash" value={shortHash(selected.block_hash, 16)} mono />
              <Row label="Prev Hash" value={shortHash(selected.prev_hash, 16)} mono />
            </dl>

            <div className="mt-6 flex flex-wrap gap-3">
              <button
                onClick={runVerify}
                disabled={verifying}
                className="inline-flex items-center gap-2 rounded-xl border border-success/50 bg-success/10 px-5 py-2.5 text-sm font-bold tracking-wide text-success transition-all hover:bg-success/20 hover:shadow-[0_0_24px_-8px_#22c55e] disabled:opacity-60"
              >
                {verifying ? <Loader2 className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
                VERIFY INTERPRETATION
              </button>
              <button
                onClick={() => {
                  setAuditFilter(selected.subject_id === "UNASSIGNED" ? null : selected.subject_id);
                  setShowAudit(true);
                }}
                className="inline-flex items-center gap-2 rounded-xl border border-cyan/40 bg-cyan/10 px-5 py-2.5 text-sm font-bold tracking-wide text-cyan transition-all hover:bg-cyan/20"
              >
                <History className="size-4" />
                VIEW AUDIT TRAIL
              </button>
              <button
                onClick={openConsent}
                className="inline-flex items-center gap-2 rounded-xl border border-violet/40 bg-violet/10 px-5 py-2.5 text-sm font-bold tracking-wide text-violet transition-all hover:bg-violet/20"
              >
                <FileSignature className="size-4" />
                VIEW CONSENT
              </button>
            </div>
          </section>

          {/* Chain re-computation panel */}
          <section className="card p-6">
            <h2 className="mb-4 text-xs font-semibold uppercase tracking-[0.25em] text-muted">
              Chain integrity re-computation
            </h2>
            {!verify && !verifying && (
              <p className="text-sm text-muted">
                Run <span className="text-success">VERIFY INTERPRETATION</span> to recompute every
                SHA-256 payload and block hash from genesis up to this record.
              </p>
            )}
            {verifying && (
              <div className="flex items-center gap-3 text-sm text-cyan">
                <Loader2 className="size-4 animate-spin" /> Recomputing hash chain…
              </div>
            )}
            <AnimatePresence>
              {verify && (
                <motion.ul initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-1.5">
                  {verify.checks.map((c, i) => (
                    <motion.li
                      key={c.block_index}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.09 }}
                      className={`mono flex items-center justify-between rounded-lg border px-3 py-2 text-xs ${
                        c.intact
                          ? "border-success/25 bg-success/5 text-success"
                          : "border-error/40 bg-error/10 text-error"
                      }`}
                    >
                      <span>
                        block #{c.block_index} · {shortHash(c.tx_id, 8)}
                      </span>
                      {c.intact ? <CheckCircle2 className="size-3.5" /> : <ShieldX className="size-3.5" />}
                    </motion.li>
                  ))}
                  <motion.li
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: verify.checks.length * 0.09 + 0.15 }}
                    className={`mt-3 rounded-xl border p-4 text-center text-sm font-black tracking-[0.2em] ${
                      verify.verified
                        ? "card-glow-success border-success/50 text-success"
                        : "border-error/50 text-error"
                    }`}
                  >
                    {verify.status} · {verify.chain_depth} BLOCKS INTACT
                  </motion.li>
                </motion.ul>
              )}
            </AnimatePresence>
          </section>
        </div>
      )}

      {/* Audit trail drawer */}
      <AnimatePresence>
        {showAudit && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex justify-end bg-bg/70"
            onClick={() => setShowAudit(false)}
          >
            <motion.aside
              initial={{ x: 480 }}
              animate={{ x: 0 }}
              exit={{ x: 480 }}
              transition={{ type: "spring", stiffness: 260, damping: 30 }}
              onClick={(e) => e.stopPropagation()}
              className="glass h-full w-[460px] overflow-y-auto p-6"
            >
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-sm font-bold uppercase tracking-[0.2em]">
                  Audit trail {auditFilter && <span className="text-cyan">· {auditFilter}</span>}
                </h3>
                <button onClick={() => setShowAudit(false)} className="text-muted hover:text-fg">
                  <X className="size-4" />
                </button>
              </div>
              <ol className="relative space-y-4 border-l border-navy-950/10 pl-5">
                {blocks
                  .filter((b) => !auditFilter || b.subject_id === auditFilter)
                  .map((b) => (
                    <li key={b.tx_id} className="relative">
                      <span
                        className={`absolute -left-[26px] top-1 size-2.5 rounded-full ${
                          b.function === "recordInterpretation" ? "bg-cyan" : "bg-violet"
                        }`}
                      />
                      <p className="mono text-xs font-semibold">
                        {b.function}() <span className="text-muted">· block #{b.block_index}</span>
                      </p>
                      <p className="text-[11px] text-muted">
                        {b.subject_id} · {timestampLabel(b.timestamp)}
                      </p>
                      <p className="mono mt-0.5 text-[10px] text-cyan/70">{shortHash(b.tx_id, 14)}</p>
                    </li>
                  ))}
              </ol>
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Consent modal */}
      <AnimatePresence>
        {consent && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 grid place-items-center bg-bg/70 p-6"
            onClick={() => setConsent(null)}
          >
            <motion.div
              initial={{ scale: 0.94, y: 12 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.94, y: 12 }}
              onClick={(e) => e.stopPropagation()}
              className="glass w-full max-w-md rounded-2xl p-6"
            >
              <div className="flex items-start justify-between">
                <h3 className="text-sm font-bold uppercase tracking-[0.2em]">
                  Consent record · {consent.patient_id}
                </h3>
                <button onClick={() => setConsent(null)} className="text-muted hover:text-fg">
                  <X className="size-4" />
                </button>
              </div>
              <div
                className={`mt-4 rounded-xl border p-4 text-center text-lg font-black tracking-[0.25em] ${
                  consent.state === "GRANTED"
                    ? "border-success/50 bg-success/10 text-success"
                    : "border-error/50 bg-error/10 text-error"
                }`}
              >
                {consent.state}
              </div>
              {consent.record && (
                <dl className="mono mt-4 space-y-2 text-[11px] text-muted">
                  {typeof consent.record.payload.scope_label === "string" && (
                    <div>
                      <dt className="text-[9px] uppercase tracking-widest text-muted/60">Scope</dt>
                      <dd className="font-sans text-fg">{consent.record.payload.scope_label}</dd>
                    </div>
                  )}
                  {typeof consent.record.payload.consent_hash === "string" && (
                    <div>
                      <dt className="text-[9px] uppercase tracking-widest text-muted/60">Consent hash</dt>
                      <dd>SHA256({shortHash(consent.record.payload.consent_hash, 14)})</dd>
                    </div>
                  )}
                  <div>
                    <dt className="text-[9px] uppercase tracking-widest text-muted/60">Recorded</dt>
                    <dd>{timestampLabel(consent.record.timestamp)} · {shortHash(consent.record.tx_id, 10)}</dd>
                  </div>
                </dl>
              )}
              <button
                onClick={toggleConsent}
                className={`mt-5 w-full rounded-xl border px-4 py-2.5 text-sm font-bold tracking-wide transition-colors ${
                  consent.state === "GRANTED"
                    ? "border-error/40 bg-error/10 text-error hover:bg-error/20"
                    : "border-success/40 bg-success/10 text-success hover:bg-success/20"
                }`}
              >
                {consent.state === "GRANTED" ? "revokeConsent()" : "recordConsent()"}
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Row({
  label,
  value,
  mono = false,
  accent = false,
  full = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
  accent?: boolean;
  full?: boolean;
}) {
  return (
    <div className={full ? "md:col-span-2" : undefined}>
      <dt className="text-[10px] font-semibold uppercase tracking-widest text-muted">{label}</dt>
      <dd
        className={`mt-0.5 break-all ${mono ? "mono text-xs" : "text-sm"} ${
          accent ? "font-semibold text-cyan" : "text-fg"
        }`}
      >
        {value}
      </dd>
    </div>
  );
}
