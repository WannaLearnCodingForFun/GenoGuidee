"use client";

import { useState } from "react";
import { ScrollText } from "lucide-react";
import { api, type ClinicalPatient } from "@/lib/api";
import { platformApi } from "@/lib/platform/client";
import { humanError } from "@/lib/platform/errors";
import type { DiseaseRankItem, GeneRankItem, PhenotypeNormalize } from "@/lib/platform/types";
import PhenotypeRanking from "@/components/platform/PhenotypeRanking";
import PhenotypeSelector, { type PhenotypeDraft } from "@/components/platform/PhenotypeSelector";
import { EmptyState, ErrorBanner, PageHeader, fieldClass, ghostBtn, primaryBtn } from "@/components/platform/ui";
import { useAccount } from "@/lib/useAccount";
import { useEffect } from "react";

function payload(drafts: PhenotypeDraft[]) {
  return drafts.map((d) => ({
    term: d.term,
    negated: d.negated,
    onset: d.onset || undefined,
    severity: d.severity || undefined,
  }));
}

export default function PhenotypeAnalysisPage() {
  const { account } = useAccount();
  const [query, setQuery] = useState("");
  const [drafts, setDrafts] = useState<PhenotypeDraft[]>([]);
  const [normalized, setNormalized] = useState<PhenotypeNormalize | null>(null);
  const [genes, setGenes] = useState<GeneRankItem[]>([]);
  const [diseases, setDiseases] = useState<DiseaseRankItem[]>([]);
  const [patients, setPatients] = useState<ClinicalPatient[]>([]);
  const [patientId, setPatientId] = useState<number | null>(null);
  const [timeline, setTimeline] = useState<Record<string, unknown>[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .clinicalPatients()
      .then((rows) => {
        setPatients(rows);
        setPatientId(rows[0]?.id ?? null);
      })
      .catch(() => setPatients([]));
  }, []);

  function add() {
    const term = query.trim();
    if (!term) return;
    setDrafts((d) => [...d, { key: `${term}-${d.length}`, term, negated: false, onset: "", severity: "" }]);
    setQuery("");
  }

  async function runMatch() {
    setBusy(true);
    setError(null);
    try {
      const terms = payload(drafts);
      const [n, g, d] = await Promise.all([
        platformApi.phenotypesNormalize(terms),
        platformApi.phenotypesRankGenes(terms, 10),
        platformApi.phenotypesRankDiseases(terms, 10),
      ]);
      setNormalized(n);
      setGenes(g.ranking ?? []);
      setDiseases(d.ranking ?? []);
    } catch (e) {
      setError(humanError(e));
    } finally {
      setBusy(false);
    }
  }

  async function loadEvolution() {
    if (patientId == null) return;
    setBusy(true);
    setError(null);
    try {
      const prof = await platformApi.phenotypesEvolutionGet(patientId, account?.role);
      const tl = Array.isArray(prof.timeline) ? (prof.timeline as Record<string, unknown>[]) : [];
      setTimeline(tl);
    } catch (e) {
      setError(humanError(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveEvolution(d: PhenotypeDraft) {
    if (patientId == null) return;
    setError(null);
    try {
      await platformApi.phenotypesEvolution(
        {
          patient_id: patientId,
          phenotype: d.term,
          status: d.negated ? "absent" : "observed",
          onset: d.onset || undefined,
          severity: d.severity || undefined,
          negated: d.negated,
        },
        account?.role,
      );
      await loadEvolution();
    } catch (e) {
      setError(humanError(e));
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-10 sm:px-8">
      <PageHeader
        icon={ScrollText}
        title="Phenotype Analysis"
        subtitle="Prioritize genes and diseases by phenotypic compatibility. This does not establish pathogenicity."
      />
      <ErrorBanner message={error} />
      <PhenotypeSelector
        query={query}
        onQuery={setQuery}
        drafts={drafts}
        onAdd={add}
        onRemove={(key) => setDrafts((d) => d.filter((x) => x.key !== key))}
        onPatch={(key, patch) => setDrafts((d) => d.map((x) => (x.key === key ? { ...x, ...patch } : x)))}
      />
      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" className={primaryBtn()} disabled={busy || drafts.length === 0} onClick={() => void runMatch()}>
          Phenotype Match
        </button>
        <button type="button" className={ghostBtn()} disabled={busy || drafts.length === 0} onClick={() => void runMatch()}>
          Gene Ranking
        </button>
        <button type="button" className={ghostBtn()} disabled={busy || drafts.length === 0} onClick={() => void runMatch()}>
          Disease Ranking
        </button>
      </div>
      {drafts.length === 0 && <div className="mt-4"><EmptyState text="No phenotype terms" /></div>}
      <div className="mt-6">
        <PhenotypeRanking normalized={normalized} genes={genes} diseases={diseases} />
      </div>
      <section className="card mt-6 p-5">
        <h2 className="text-sm font-semibold">Phenotype evolution</h2>
        <p className="mt-1 text-xs text-muted">Persisted HPO observations for a clinical patient. ACMG is not recalculated here.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <select
            className={fieldClass() + " max-w-xs"}
            value={patientId ?? ""}
            onChange={(e) => setPatientId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">No patient</option>
            {patients.map((p) => (
              <option key={p.id} value={p.id}>
                {p.identifier}
              </option>
            ))}
          </select>
          <button type="button" className={ghostBtn()} onClick={() => void loadEvolution()}>
            Load timeline
          </button>
          {drafts[0] && (
            <button type="button" className={ghostBtn()} onClick={() => void saveEvolution(drafts[0])}>
              Persist first term
            </button>
          )}
        </div>
        {timeline.length === 0 ? (
          <div className="mt-3">
            <EmptyState text="No phenotype evolution recorded for this patient." />
          </div>
        ) : (
          <ul className="mt-3 space-y-1 text-xs">
            {timeline.map((t, i) => (
              <li key={i}>
                {String(t.phenotype ?? "")} · {String(t.hpo_id ?? "unresolved")} · {String(t.status ?? "")}
                {t.negated ? " · absent" : ""}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
