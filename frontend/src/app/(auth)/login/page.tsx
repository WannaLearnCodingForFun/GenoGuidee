"use client";

import { Suspense, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, Loader2, LogIn } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { api, setLocalToken } from "@/lib/api";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [patientId, setPatientId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    if (!isSupabaseConfigured()) {
      try {
        const res = await api.login({
          email,
          password,
          patient_id: patientId.trim() || undefined,
        });
        setLocalToken(res.token);
        router.push(params.get("next") ?? "/dashboard");
        router.refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Login failed");
      }
      setLoading(false);
      return;
    }

    const supabase = createClient();
    const { error } = await supabase.auth.signInWithPassword({ email, password });

    setLoading(false);
    if (error) {
      setError(error.message);
      return;
    }

    router.push(params.get("next") ?? "/dashboard");
    router.refresh();
  }

  return (
    <div className="card p-8">
      <h1 className="text-2xl font-bold tracking-tight">Sign in</h1>
      <p className="mt-1 text-sm text-muted">
        Doctors and lab technicians sign in with email and password. Patients must also enter their Patient ID.
      </p>

      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        <div>
          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-muted">
            Email
          </label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-cyan/50"
            placeholder="you@example.com"
          />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-muted">
            Patient ID
          </label>
          <input
            value={patientId}
            onChange={(e) => setPatientId(e.target.value.trim())}
            className="w-full rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-cyan/50"
            placeholder="PAT-2026-000001 — patients only"
            autoComplete="off"
          />
          <p className="mt-1 text-[11px] text-muted">Required for patient accounts. Leave blank if you are a doctor or lab technician.</p>
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-muted">
            Password
          </label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-cyan/50"
            placeholder="••••••••"
          />
        </div>

        {error && <p className="text-sm text-error">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="group flex w-full items-center justify-center gap-2 rounded-xl border border-cyan/40 bg-cyan/10 px-6 py-3 text-sm font-semibold text-cyan transition-all hover:bg-cyan/20 hover:shadow-[0_0_32px_-8px_#b4182d] disabled:opacity-60"
        >
          {loading ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <LogIn className="size-4" />
          )}
          Sign in
          <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-muted">
        Don&apos;t have an account?{" "}
        <Link href="/signup" className="text-cyan hover:underline">
          Create one
        </Link>
      </p>
      {!isSupabaseConfigured() && (
        <p className="mt-3 text-center text-[11px] uppercase tracking-widest text-muted">
          Local accounts are stored in the clinical database
        </p>
      )}
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="card p-8 text-sm text-muted">Loading…</div>}>
      <LoginForm />
    </Suspense>
  );
}
