"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { GitCompare } from "lucide-react";
import { platformApi } from "@/lib/platform/client";
import { humanError } from "@/lib/platform/errors";
import { rememberInterpretationId } from "@/lib/platform/session";
import type { InterpretationDiff, InterpretationVersion } from "@/lib/platform/types";
import InterpretationDiffView from "@/components/platform/InterpretationDiff";
import { ErrorBanner, PageHeader, SkeletonCard } from "@/components/platform/ui";

export default function InterpretationHistoryPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const [versions, setVersions] = useState<InterpretationVersion[]>([]);
  const [a, setA] = useState(1);
  const [b, setB] = useState(1);
  const [diff, setDiff] = useState<InterpretationDiff | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    rememberInterpretationId(id);
    let cancelled = false;
    platformApi
      .history(id)
      .then((h) => {
        if (cancelled) return;
        setVersions(h.versions);
        if (h.versions.length) {
          setA(h.versions[0].version);
          setB(h.versions[h.versions.length - 1].version);
        }
        setError(null);
      })
      .catch((e) => {
        if (!cancelled) setError(humanError(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  useEffect(() => {
    if (!id || a === b) return;
    let cancelled = false;
    platformApi
      .diff(id, a, b)
      .then((d) => {
        if (!cancelled) setDiff(d);
      })
      .catch((e) => {
        if (!cancelled) setError(humanError(e));
      });
    return () => {
      cancelled = true;
    };
  }, [id, a, b]);

  const shown = a === b ? null : diff;

  return (
    <div className="mx-auto max-w-7xl px-6 py-10 sm:px-8">
      <PageHeader
        icon={GitCompare}
        title="Interpretation history"
        subtitle="Compare persisted interpretation versions. History is never rewritten."
      />
      <ErrorBanner message={error} />
      {loading ? <SkeletonCard /> : <InterpretationDiffView versions={versions} diff={shown} a={a} b={b} onChangeA={setA} onChangeB={setB} />}
    </div>
  );
}
