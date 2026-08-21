"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Dna,
  FlaskConical,
  Network,
  ShieldCheck,
  UserRound,
  CheckCircle2,
} from "lucide-react";
import { api, type SystemStatus } from "@/lib/api";

const NAV = [
  { href: "/", label: "Overview", icon: Activity },
  { href: "/variant-lab", label: "Variant Lab", icon: FlaskConical },
  { href: "/patient-context", label: "Patient Context", icon: UserRound },
  { href: "/knowledge-graph", label: "Knowledge Graph", icon: Network },
  { href: "/provenance", label: "Provenance", icon: ShieldCheck },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [status, setStatus] = useState<SystemStatus | null>(null);

  useEffect(() => {
    api.status().then(setStatus).catch(() => setStatus(null));
  }, []);

  return (
    <aside className="fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-white/8 bg-panel/80">
      <Link href="/" className="flex items-center gap-3 px-5 py-6">
        <span className="grid size-9 place-items-center rounded-xl border border-cyan/30 bg-cyan/10 shadow-[0_0_18px_-4px_#00e5ff]">
          <Dna className="size-5 text-cyan" />
        </span>
        <span>
          <span className="block text-sm font-bold tracking-[0.22em]">GENOGUIDE</span>
          <span className="block text-[10px] uppercase tracking-widest text-muted">
            Genomic Intelligence
          </span>
        </span>
      </Link>

      <nav className="mt-2 flex flex-col gap-1 px-3">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
                active
                  ? "border border-cyan/25 bg-cyan/10 text-cyan shadow-[0_0_16px_-6px_#00e5ff]"
                  : "border border-transparent text-muted hover:bg-white/5 hover:text-fg"
              }`}
            >
              <Icon className="size-4" />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto space-y-3 px-4 pb-5">
        <div className="card p-3">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-muted">
            System status
          </p>
          <ul className="space-y-1.5">
            {(status?.components ?? [
              { name: "ESM-2", ready: false },
              { name: "XGBoost", ready: false },
              { name: "ACMG Engine", ready: false },
              { name: "Provenance", ready: false },
            ]).map((c) => (
              <li key={c.name} className="flex items-center justify-between text-xs">
                <span className="text-muted">{c.name}</span>
                {c.ready ? (
                  <span className="flex items-center gap-1 text-success">
                    <CheckCircle2 className="size-3" /> READY
                  </span>
                ) : (
                  <span className="text-warning">CONNECTING…</span>
                )}
              </li>
            ))}
          </ul>
        </div>
        <div className="flex items-center justify-between text-[10px] uppercase tracking-widest">
          <span className="rounded border border-violet/40 bg-violet/10 px-2 py-1 text-violet">
            {status?.mode ?? "OFFLINE"}
          </span>
          <span className="text-muted">v1.0</span>
        </div>
      </div>
    </aside>
  );
}
