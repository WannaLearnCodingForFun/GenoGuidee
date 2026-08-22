"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";

const ROLE_LABEL: Record<string, string> = {
  doctor: "Doctor",
  patient: "Patient",
  lab_technician: "Lab Technician",
};

export default function Overview() {
  const [offline, setOffline] = useState(false);
  const [account, setAccount] = useState<{ name: string; detail: string } | null>(null);

  useEffect(() => {
    api.status().catch(() => setOffline(true));
  }, []);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getUser().then(async ({ data: { user } }) => {
      if (!user) return;

      const { data: profile } = await supabase
        .from("profiles")
        .select("role")
        .eq("id", user.id)
        .single();

      // Accounts created before the profiles table/trigger existed have no
      // row here yet — fall back to the role stashed in signup metadata so
      // older sessions still show something instead of staying blank.
      const role = profile?.role ?? (user.user_metadata?.role as string | undefined);
      const username = user.email?.split("@")[0] ?? "there";

      setAccount({
        name: username,
        detail: role ? (ROLE_LABEL[role] ?? role) : "Account",
      });
    });
  }, []);

  return (
    <div className="relative min-h-screen overflow-hidden">
      {/* Hero background */}
      <div className="absolute inset-0 grid-texture" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_30%_20%,rgba(180,24,45,0.07),transparent_70%)]" />

      <div className="relative z-10 mx-auto max-w-6xl px-8 py-14">
        {/* Hero */}
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: "easeOut" }}
          className="flex items-start justify-between gap-4"
        >
          <div>
            <h1 className="text-5xl font-black tracking-tight">
              Welcome, <span className="text-gradient">{account?.name ?? "…"}</span>
            </h1>

            {offline && (
              <p className="mt-4 text-sm text-warning">
                Backend not reachable — start it with{" "}
                <code className="mono rounded bg-navy-950/5 px-1.5 py-0.5">uvicorn app.main:app --port 8000</code>
              </p>
            )}
          </div>

          {account?.detail && (
            <span className="mt-2 shrink-0 rounded-full border border-cyan/25 bg-cyan/5 px-4 py-1.5 text-xs font-semibold uppercase tracking-widest text-cyan">
              {account.detail}
            </span>
          )}
        </motion.div>
      </div>
    </div>
  );
}
