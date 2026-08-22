"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, FlaskConical, Loader2, Stethoscope, UserRound, UserPlus } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

type Role = "doctor" | "patient" | "lab_technician";

const ROLES: { id: Role; label: string; icon: typeof Stethoscope }[] = [
  { id: "doctor", label: "Doctor", icon: Stethoscope },
  { id: "patient", label: "Patient", icon: UserRound },
  { id: "lab_technician", label: "Lab Technician", icon: FlaskConical },
];

export default function SignupPage() {
  const router = useRouter();
  const [role, setRole] = useState<Role>("doctor");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // role-specific fields
  const [licenseNumber, setLicenseNumber] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [labName, setLabName] = useState("");
  const [certificationId, setCertificationId] = useState("");

  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [checkEmail, setCheckEmail] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const metadata: Record<string, string> = { role, full_name: fullName };
    if (role === "doctor") {
      metadata.license_number = licenseNumber;
      if (specialty) metadata.specialty = specialty;
    } else if (role === "patient") {
      if (dateOfBirth) metadata.date_of_birth = dateOfBirth;
    } else if (role === "lab_technician") {
      metadata.lab_name = labName;
      if (certificationId) metadata.certification_id = certificationId;
    }

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

    if (data.session) {
      router.push("/dashboard");
      router.refresh();
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
          activate your {ROLES.find((r) => r.id === role)?.label.toLowerCase()} account.
        </p>
      </div>
    );
  }

  return (
    <div className="card p-8">
      <h1 className="text-2xl font-bold tracking-tight">Create an account</h1>
      <p className="mt-1 text-sm text-muted">Choose your role to get the right access.</p>

      <div className="mt-5 grid grid-cols-3 gap-2">
        {ROLES.map((r) => (
          <button
            key={r.id}
            type="button"
            onClick={() => setRole(r.id)}
            className={`flex flex-col items-center gap-1.5 rounded-xl border px-3 py-3 text-xs font-medium transition-colors ${
              role === r.id
                ? "border-cyan/40 bg-cyan/10 text-cyan"
                : "border-navy-950/10 text-muted hover:border-navy-950/20 hover:text-fg"
            }`}
          >
            <r.icon className="size-4" />
            {r.label}
          </button>
        ))}
      </div>

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

        {role === "doctor" && (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-muted">
                License number
              </label>
              <input
                required
                value={licenseNumber}
                onChange={(e) => setLicenseNumber(e.target.value)}
                className="w-full rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-cyan/50"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-muted">
                Specialty
              </label>
              <input
                value={specialty}
                onChange={(e) => setSpecialty(e.target.value)}
                className="w-full rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-cyan/50"
                placeholder="Clinical genetics"
              />
            </div>
          </div>
        )}

        {role === "patient" && (
          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-muted">
              Date of birth
            </label>
            <input
              type="date"
              value={dateOfBirth}
              onChange={(e) => setDateOfBirth(e.target.value)}
              className="w-full rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-cyan/50"
            />
          </div>
        )}

        {role === "lab_technician" && (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-muted">
                Lab name
              </label>
              <input
                required
                value={labName}
                onChange={(e) => setLabName(e.target.value)}
                className="w-full rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-cyan/50"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-muted">
                Certification ID
              </label>
              <input
                value={certificationId}
                onChange={(e) => setCertificationId(e.target.value)}
                className="w-full rounded-lg border border-navy-950/10 bg-panel2 px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-cyan/50"
              />
            </div>
          </div>
        )}

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
