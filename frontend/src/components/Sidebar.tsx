"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import {
  Activity,
  Dna,
  FlaskConical,
  LogOut,
  Network,
  Pill,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { createClient } from "@/lib/supabase/client";

const ROLE_LABEL: Record<string, string> = {
  doctor: "Doctor",
  patient: "Patient",
  lab_technician: "Lab Technician",
};

const NAV = [
  { href: "/dashboard", label: "Overview", icon: Activity },
  { href: "/variant-lab", label: "Variant Lab", icon: FlaskConical },
  { href: "/patient-context", label: "Patient Context", icon: UserRound },
  { href: "/therapy", label: "Therapy Ranking", icon: Pill },
  { href: "/knowledge-graph", label: "Knowledge Graph", icon: Network },
  { href: "/provenance", label: "Provenance", icon: ShieldCheck },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [account, setAccount] = useState<{ name: string; role: string; email: string } | null>(
    null,
  );

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getUser().then(async ({ data: { user } }) => {
      if (!user) return;
      const { data: profile } = await supabase
        .from("profiles")
        .select("role, full_name")
        .eq("id", user.id)
        .single();
      setAccount({
        name: profile?.full_name || user.email || "Account",
        role: profile?.role ?? "",
        email: user.email ?? "",
      });
    });
  }, []);

  async function signOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <aside className="fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-navy-950/8 bg-panel/80">
      <Link href="/dashboard" className="flex items-center gap-3 px-5 py-6">
        <span className="grid size-9 place-items-center rounded-xl border border-cyan/30 bg-cyan/10 shadow-[0_0_18px_-4px_#b4182d]">
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
                  ? "border border-cyan/25 bg-cyan/10 text-cyan shadow-[0_0_16px_-6px_#b4182d]"
                  : "border border-transparent text-muted hover:bg-navy-950/5 hover:text-fg"
              }`}
            >
              <Icon className="size-4" />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto space-y-3 px-4 pb-5">
        {account && (
          <div className="card flex items-center justify-between gap-2 p-3">
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold">{account.name}</p>
              <p className="truncate text-[10px] uppercase tracking-widest text-cyan">
                {ROLE_LABEL[account.role] ?? account.role}
              </p>
            </div>
            <button
              onClick={signOut}
              title="Sign out"
              className="grid size-7 shrink-0 place-items-center rounded-lg border border-navy-950/10 text-muted transition-colors hover:border-error/40 hover:text-error"
            >
              <LogOut className="size-3.5" />
            </button>
          </div>
        )}
        <div className="text-right text-[10px] uppercase tracking-widest text-muted">v1.0</div>
      </div>
    </aside>
  );
}
