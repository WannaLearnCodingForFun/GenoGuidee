"use client";

import type { DiseaseRankItem, GeneRankItem, PhenotypeNormalize } from "@/lib/platform/types";
import { EmptyState } from "@/components/platform/ui";

export default function PhenotypeRanking({
  normalized,
  genes,
  diseases,
}: {
  normalized: PhenotypeNormalize | null;
  genes: GeneRankItem[];
  diseases: DiseaseRankItem[];
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <section className="card p-5">
        <h3 className="text-sm font-semibold">Normalized terms</h3>
        {!normalized && <p className="mt-2 text-xs text-muted">Run phenotype match to normalize terms.</p>}
        {normalized && (
          <ul className="mt-2 space-y-1 text-xs">
            {normalized.terms.map((t, i) => (
              <li key={`${t.input}-${i}`}>
                {t.input} → {t.resolved ? `${t.hpo_id} ${t.label}` : "unresolved"}
                {t.negated ? " (absent)" : ""}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="card p-5">
        <h3 className="text-sm font-semibold">Top genes</h3>
        <p className="text-[10px] uppercase tracking-widest text-muted">Candidate association</p>
        {genes.length === 0 ? (
          <div className="mt-2">
            <EmptyState text="No phenotype terms produced a gene ranking." />
          </div>
        ) : (
          <ul className="mt-2 space-y-2 text-sm">
            {genes.map((g) => (
              <li key={g.gene} className="flex justify-between gap-2">
                <span>{g.gene}</span>
                <span className="mono text-xs text-muted">{g.phenotype_match_score ?? "—"}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="card p-5">
        <h3 className="text-sm font-semibold">Top diseases</h3>
        <p className="text-[10px] uppercase tracking-widest text-muted">Phenotypic compatibility</p>
        {diseases.length === 0 ? (
          <div className="mt-2">
            <EmptyState text="No phenotype terms produced a disease ranking." />
          </div>
        ) : (
          <ul className="mt-2 space-y-2 text-sm">
            {diseases.map((d) => (
              <li key={d.disease_id}>
                <span className="font-semibold">{d.disease_name}</span>
                <span className="mono ml-2 text-xs text-muted">{d.phenotype_match_score}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
