"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { platformApi } from "@/lib/platform/client";
import { humanError } from "@/lib/platform/errors";
import { writePlatformSession } from "@/lib/platform/session";
import { useAccount } from "@/lib/useAccount";
import type { ReanalysisChange, ReanalysisCheck, ReanalysisRun } from "@/lib/platform/types";
import ReanalysisChangeCard from "@/components/platform/ReanalysisChangeCard";
import { EmptyState, ErrorBanner, PageHeader, SkeletonCard, ghostBtn, primaryBtn } from "@/components/platform/ui";

export default function ReanalysisPage() {
  const { account } = useAccount();
  const [check, setCheck] = useState<ReanalysisCheck | null>(null);
  const [run, setRun] = useState<ReanalysisRun | null>(null);
  const [changes, setChanges] = useState<ReanalysisChange[]>([]);
  const [watchCount, setWatchCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const role = account?.role;

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      platformApi.reanalysisCheck(),
      platformApi.reanalysisChanges(),
      platformApi.watchlistList(role),
    ])
      .then(([c, ch, w]) => {
        if (cancelled) return;
        setCheck(c);
        setChanges(ch.changes);
        setWatchCount(w.items.length);
      })
      .catch((e) => {
        if (!cancelled) setError(humanError(e));
      });
    return () => {
      cancelled = true;
    };
  }, [role]);

  async function refresh() {
    setBusy("refresh");
    setError(null);
    try {
      const [c, ch, w] = await Promise.all([
        platformApi.reanalysisCheck(),
        platformApi.reanalysisChanges(),
        platformApi.watchlistList(role),
      ]);
      setCheck(c);
      setChanges(ch.changes);
      setWatchCount(w.items.length);
    } catch (e) {
      setError(humanError(e));
    } finally {
      setBusy(null);
    }
  }

  async function runReanalysis() {
    setBusy("run");
    setError(null);
    try {
      const result = await platformApi.reanalysisRun();
      setRun(result);
      const ch = await platformApi.reanalysisChanges();
      setChanges(ch.changes);
      const c = await platformApi.reanalysisCheck();
      setCheck(c);
    } catch (e) {
      setError(humanError(e));
    } finally {
      setBusy(null);
    }
  }

  const pending = changes.filter((c) => c.change_type !== "NO_CHANGE").length;
  const reviews = changes.filter((c) => Boolean(c.payload.review_required)).length;
  const last = changes[0]?.created_at;

  return (
    <div className="mx-auto max-w-7xl px-6 py-10 sm:px-8">
      <PageHeader
        icon={RefreshCw}
        title="Continuous Reanalysis"
        subtitle="Track how genomic knowledge changes your interpretations over time."
        actions={
          <div className="flex flex-wrap gap-2">
            <button type="button" className={ghostBtn()} disabled={!!busy} onClick={() => void refresh()}>
              Check for Updates
            </button>
            <button type="button" className={primaryBtn()} disabled={!!busy} onClick={() => void runReanalysis()}>
              Run Reanalysis
            </button>
            <button type="button" className={ghostBtn()} disabled={!!busy} onClick={() => void refresh()}>
              Refresh
            </button>
          </div>
        }
      />
      <ErrorBanner message={error} />
      {busy && <p className="mb-4 text-sm text-muted">Working: {busy}…</p>}
      {!check && !error && busy ? (
        <div className="grid gap-3 sm:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : (
        <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <div className="card p-4">
            <p className="text-[10px] uppercase tracking-widest text-muted">Last checked</p>
            <p className="mt-2 text-sm font-semibold">{last ? new Date(last * 1000).toLocaleString() : "Never"}</p>
          </div>
          <div className="card p-4">
            <p className="text-[10px] uppercase tracking-widest text-muted">Sources checked</p>
            <p className="mt-2 text-lg font-bold">{check ? Object.keys(check.sources).length : 0}</p>
          </div>
          <div className="card p-4">
            <p className="text-[10px] uppercase tracking-widest text-muted">Variants monitored</p>
            <p className="mt-2 text-lg font-bold">{watchCount}</p>
          </div>
          <div className="card p-4">
            <p className="text-[10px] uppercase tracking-widest text-muted">Pending changes</p>
            <p className="mt-2 text-lg font-bold">{pending}</p>
          </div>
          <div className="card p-4">
            <p className="text-[10px] uppercase tracking-widest text-muted">Human reviews required</p>
            <p className="mt-2 text-lg font-bold">{reviews}</p>
          </div>
        </div>
      )}
      {run && (
        <p className="mb-4 text-xs text-muted">
          Job {run.job_id} {run.status}. Auto-finalized: {run.auto_finalized ? "yes" : "no"}.
        </p>
      )}
      <div className="mb-4">
        <button
          type="button"
          className={ghostBtn()}
          onClick={async () => {
            const vid = prompt("Variant ID to watch");
            if (!vid) return;
            try {
              await platformApi.watchlistAdd({ variant_id: vid }, account?.role);
              writePlatformSession({ variantId: vid });
              await refresh();
            } catch (e) {
              setError(humanError(e));
            }
          }}
        >
          Add to watchlist
        </button>
      </div>
      <h2 className="mb-3 text-sm font-semibold">Change feed</h2>
      {changes.length === 0 ? (
        <EmptyState text="No reanalysis changes detected" />
      ) : (
        <div className="grid gap-3">
          {changes.map((c, i) => (
            <ReanalysisChangeCard key={`${c.job_id}-${c.variant_id}-${i}`} change={c} />
          ))}
        </div>
      )}
    </div>
  );
}
