"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { api, getLocalToken, setLocalToken } from "@/lib/api";

export type Role = "doctor" | "patient" | "lab_technician" | "";

export interface Account {
  id: string;
  name: string;
  role: Role;
  email: string;
}

export function useAccount() {
  const [account, setAccount] = useState<Account | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    if (!isSupabaseConfigured()) {
      if (!getLocalToken()) {
        setLoading(false);
        return;
      }
      api.me()
        .then((u) => {
          if (cancelled) return;
          setAccount({
            id: String(u.id),
            name: u.full_name,
            role: u.role as Role,
            email: u.email,
          });
          setLoading(false);
        })
        .catch(() => {
          setLocalToken(null);
          if (!cancelled) setLoading(false);
        });
      return;
    }
    const supabase = createClient();
    supabase.auth.getUser().then(async ({ data: { user } }: { data: { user: { id: string; email?: string | null; user_metadata?: Record<string, unknown> } | null } }) => {
      if (!user) {
        if (!cancelled) setLoading(false);
        return;
      }
      const { data: profile } = await supabase
        .from("profiles")
        .select("role, full_name")
        .eq("id", user.id)
        .single();
      const role = (profile?.role ?? (user.user_metadata?.role as string | undefined) ?? "") as Role;
      const fullName = profile?.full_name || (user.user_metadata?.full_name as string | undefined);
      if (cancelled) return;
      setAccount({
        id: user.id,
        name: fullName || user.email || "Account",
        role,
        email: user.email ?? "",
      });
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return { account, loading };
}
