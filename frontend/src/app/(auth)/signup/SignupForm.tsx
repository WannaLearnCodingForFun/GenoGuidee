"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import Link from "next/link";
import { ArrowRight, Loader2, UserPlus } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

export type Role = "doctor" | "patient" | "lab_technician";

const REF_PREFIX: Record<Role, string> = {
  doctor: "DOC",
  patient: "MRN",
  lab_technician: "LAB",
};

const ROLE_LABEL: Record<Role, string> = {
  doctor: "doctor",
  patient: "patient",
  lab_technician: "lab technician",
};

export function SignupForm({
  role,
  extraFields,
  buildMetadata,
}: {
  role: Role;
  extraFields?: ReactNode;
  buildMetadata: () => Record<string, string>;
}) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [checkEmail, setCheckEmail] = useState(false);
  const [referenceId, setReferenceId] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const metadata: Record<string, string> = { role, full_name: fullName, ...buildMetadata() };

    const supabase = createClient();
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: metadata,
        emailRedirectTo: `${window.location.origin}/auth/callback?next=/dashboard`,
      },
    });

    setLoading(false);
    if (error) {
      setError(error.message);
      return;
    }

    const userId = data.user?.id;
    if (userId) {
      setReferenceId(`${REF_PREFIX[role]}-${userId.slice(0, 8).toUpperCase()}`);
    }

    if (data.session) {
      window.location.href = "/dashboard";
    } else {
      setCheckEmail(true);
    }
  }

  if (checkEmail) {
    return (
      <div className="card p-8 text-center">
        <h1 className="text-2xl font-bold tracking-tight">Check your email</h1>
        <p className="mt-2 text-sm text-muted">
          We sent a confirmation link to <span className="text-fg">{email}</span>. Follow it to
          activate your {ROLE_LABEL[role]} account.
        </p>
        {referenceId && (
          <p className="mt-4 rounded-lg border border-cyan/30 bg-cyan/10 p-3 text-sm text-cyan">
            Your {ROLE_LABEL[role]} reference ID is <span className="font-mono font-semibold">{referenceId}</span> —
            keep it for your records.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="card p-8">
      <h1 className="text-2xl font-bold tracking-tight">Create a {ROLE_LABEL[role]} account</h1>
      <p className="mt-1 text-sm text-muted">
        Not a {ROLE_LABEL[role]}?{" "}
        <Link href="/signup" className="text-cyan hover:underline">
          Choose a different role
        </Link>
      </p>

      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        <div>
          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-muted">
            Full name
          </label>
          <input
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="w-full rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-cyan/50"
            placeholder="Jane Doe"
          />
        </div>
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
            Password
          </label>
          <input
            type="password"
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-cyan/50"
            placeholder="••••••••"
          />
        </div>

        {extraFields}

        {error && <p className="text-sm text-error">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="group flex w-full items-center justify-center gap-2 rounded-xl border border-cyan/40 bg-cyan/10 px-6 py-3 text-sm font-semibold text-cyan transition-all hover:bg-cyan/20 hover:shadow-[0_0_32px_-8px_#b4182d] disabled:opacity-60"
        >
          {loading ? <Loader2 className="size-4 animate-spin" /> : <UserPlus className="size-4" />}
          Create account
          <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-muted">
        Already have an account?{" "}
        <Link href="/login" className="text-cyan hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}

export const fieldLabelClass =
  "mb-1.5 block text-xs font-semibold uppercase tracking-widest text-muted";
export const fieldInputClass =
  "w-full rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-cyan/50";
