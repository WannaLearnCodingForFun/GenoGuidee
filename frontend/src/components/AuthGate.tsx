"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { getLocalToken } from "@/lib/api";
import { useAccount } from "@/lib/useAccount";
import { pathAllowedForRole } from "@/lib/nav";

const PROTECTED_PREFIXES = [
  "/dashboard",
  "/upload",
  "/clinical-workup",
  "/variant-lab",
  "/patient-context",
  "/knowledge-graph",
  "/provenance",
  "/therapy",
];

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { account, loading } = useAccount();
  const pathname = usePathname();
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const protectedPath = PROTECTED_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );
  const supabase = isSupabaseConfigured();

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted || !protectedPath) return;
    const token = getLocalToken();
    if (!supabase && !token) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      return;
    }
    if (loading) return;
    if (!account) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      return;
    }
    if (!pathAllowedForRole(account.role, pathname)) {
      router.replace("/unauthorized");
    }
  }, [account, loading, mounted, pathname, protectedPath, router, supabase]);

  if (!protectedPath) return <>{children}</>;
  if (!mounted || loading) {
    return <div className="px-8 py-12 text-sm text-muted">Checking session…</div>;
  }
  if (!supabase && !getLocalToken()) {
    return <div className="px-8 py-12 text-sm text-muted">Redirecting to login…</div>;
  }
  if (!account) {
    return <div className="px-8 py-12 text-sm text-muted">Redirecting to login…</div>;
  }
  if (!pathAllowedForRole(account.role, pathname)) {
    return <div className="px-8 py-12 text-sm text-muted">Redirecting…</div>;
  }
  return <>{children}</>;
}
