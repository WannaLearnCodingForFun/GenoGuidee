"use client";

import { useCallback, useEffect, useState } from "react";
import { Layers } from "lucide-react";
import { platformApi } from "@/lib/platform/client";
import { humanError } from "@/lib/platform/errors";
import { rememberInterpretationId, rememberedInterpretationIds } from "@/lib/platform/session";
import type { InterpretationVersion } from "@/lib/platform/types";
import CurationQueue, { type CurationQueueId } from "@/components/platform/CurationQueue";
import CurationReview from "@/components/platform/CurationReview";
import { EmptyState, ErrorBanner, PageHeader, fieldClass, ghostBtn } from "@/components/platform/ui";
import { useAccount } from "@/lib/useAccount";

export default function CurationPage() {
  const { account } = useAccount();
  const [ids, setIds] = useState<string[]>([]);
  const [lookup, setLookup] = useState("");
  const [latest, setLatest] = useState<InterpretationVersion[]>([]);
  const [queue, setQueue] = useState<CurationQueueId>("AI_DRAFT");
  const [selected, setSelected] = useState<string | null>(null);
  const [current, setCurrent] = useState<InterpretationVersion | null>(null);
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);
  const [error, setError] = useState<string | null>(null);

  const loadAll = useCallback(async (list: string[]) => {
    const rows: InterpretationVersion[] = [];
    for (const id of list) {
      try {
        const h = await platformApi.history(id);
        const last = h.versions[h.versions.length - 1];
        if (last) rows.push(last);
      } catch {
        /* missing ids stay out of the queue */
      }
    }
    setLatest(rows);
  }, []);

  useEffect(() => {
    const remembered = rememberedInterpretationIds();
    let cancelled = false;
    platformApi
      .reanalysisChanges()
      .then((ch) => {
        if (cancelled) return;
        const fromChanges = ch.changes.map((c) => c.interpretation_id).filter((x): x is string => !!x);
        const merged = [...new Set([...remembered, ...fromChanges])];
        setIds(merged);
        return loadAll(merged);
      })
      .catch((e) => {
        if (!cancelled) setError(humanError(e));
      });
    return () => {
      cancelled = true;
    };
  }, [loadAll]);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    Promise.all([platformApi.history(selected), platformApi.curationEvents(selected)])
      .then(([h, ev]) => {
        if (cancelled) return;
        const last = h.versions[h.versions.length - 1] ?? null;
        setCurrent(last);
        setEvents(ev.events);
        if (last) {
          setLatest((prev) => [last, ...prev.filter((p) => p.interpretation_id !== selected)]);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(humanError(e));
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  async function refreshSelected() {
    if (!selected) return;
    try {
      const [h, ev] = await Promise.all([platformApi.history(selected), platformApi.curationEvents(selected)]);
      setCurrent(h.versions[h.versions.length - 1] ?? null);
      setEvents(ev.events);
      setLatest((prev) => {
        const last = h.versions[h.versions.length - 1];
        if (!last) return prev;
        return [last, ...prev.filter((p) => p.interpretation_id !== selected)];
      });
    } catch (e) {
      setError(humanError(e));
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-10 sm:px-8">
      <PageHeader
        icon={Layers}
        title="Curation Workspace"
        subtitle="Laboratory review of AI drafts, conflicts, and finalized interpretations."
      />
      <ErrorBanner message={error} />
      <div className="mb-4 flex flex-wrap gap-2">
        <input
          className={`${fieldClass()} max-w-md`}
          value={lookup}
          onChange={(e) => setLookup(e.target.value)}
          placeholder="Interpretation ID"
        />
        <button
          type="button"
          className={ghostBtn()}
          onClick={() => {
            const id = lookup.trim();
            if (!id) return;
            rememberInterpretationId(id);
            setIds((prev) => [id, ...prev.filter((x) => x !== id)]);
            void loadAll([id, ...ids.filter((x) => x !== id)]);
            setSelected(id);
          }}
        >
          Open case
        </button>
      </div>
      {latest.length === 0 ? (
        <EmptyState text="No pending curation cases. Interpret a variant, run reanalysis, or open an interpretation ID." />
      ) : (
        <CurationQueue
          latest={latest}
          activeQueue={queue}
          selectedId={selected}
          onQueue={setQueue}
          onSelect={(id) => {
            setSelected(id);
            rememberInterpretationId(id);
          }}
        />
      )}
      <div className="mt-8">
          <CurationReview current={current} events={events} role={account?.role ?? ""} onRefresh={() => void refreshSelected()} />
      </div>
    </div>
  );
}
