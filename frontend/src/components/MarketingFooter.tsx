import Link from "next/link";
import { Dna } from "lucide-react";

const COLUMNS = [
  {
    title: "Product",
    links: [
      { label: "Variant Lab", href: "/variant-lab" },
      { label: "Patient Context", href: "/patient-context" },
      { label: "Knowledge Graph", href: "/knowledge-graph" },
      { label: "Provenance Ledger", href: "/provenance" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "How it works", href: "/#how-it-works" },
      { label: "Security", href: "/#security" },
      { label: "FAQ", href: "/#faq" },
      { label: "Launch app", href: "/dashboard" },
    ],
  },
];

export default function MarketingFooter() {
  return (
    <footer className="bg-navy-950">
      <div className="mx-auto max-w-6xl px-6 py-14 lg:px-8">
        <div className="grid gap-10 md:grid-cols-[1.4fr_1fr_1fr]">
          <div>
            <div className="flex items-center gap-3">
              <span className="grid size-8 place-items-center rounded-lg border border-coral/30 bg-coral/10">
                <Dna className="size-4 text-coral" />
              </span>
              <span className="text-sm font-bold tracking-[0.22em] text-white">GENOGUIDE</span>
            </div>
            <p className="mt-4 max-w-sm text-sm text-white/60">
              AI-powered genomic variant interpretation, reconciled against a deterministic
              ACMG/AMP rule engine and sealed on a hash-chained provenance ledger.
            </p>
          </div>
          {COLUMNS.map((col) => (
            <div key={col.title}>
              <h4 className="text-xs font-semibold uppercase tracking-[0.25em] text-white/50">
                {col.title}
              </h4>
              <ul className="mt-4 space-y-2.5">
                {col.links.map((l) => (
                  <li key={l.label}>
                    <Link
                      href={l.href}
                      className="text-sm text-white/70 transition-colors hover:text-coral"
                    >
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 flex flex-col gap-3 border-t border-white/10 pt-6 text-xs text-white/50 md:flex-row md:items-center md:justify-between">
          <p>© {new Date().getFullYear()} GenoGuide. All patient records shown are synthetic demo data.</p>
          <p className="mono">v1.0 · demo mode</p>
        </div>
      </div>
    </footer>
  );
}
