"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

export type Role = "doctor" | "patient" | "lab_technician" | "";

export interface Account {
  id: string;
  name: string;
  role: Role;
  email: string;
}

/** Session + profile row for the signed-in user. `id` is the Supabase auth
 * uid, which is also the primary key of the matching patients/doctors/
 * lab_technicians row (Phase B1/B2 shared identity source). */
export function useAccount() {
  const [account, setAccount] = useState<Account | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const supabase = createClient();
    supabase.auth.getUser().then(async ({ data: { user } }) => {
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
