import Link from "next/link";
import { FlaskConical, Stethoscope, UserRound } from "lucide-react";

const ROLES = [
  { href: "/signup/doctor", label: "Doctor", icon: Stethoscope, desc: "Manage patients, review interpretations, sign off on findings." },
  { href: "/signup/patient", label: "Patient", icon: UserRound, desc: "Upload your VCF and track your results in plain language." },
  { href: "/signup/lab-technician", label: "Lab Technician", icon: FlaskConical, desc: "Process lab orders assigned to you." },
] as const;

export default function SignupRolePickerPage() {
  return (
    <div className="card p-8">
      <h1 className="text-2xl font-bold tracking-tight">Create an account</h1>
      <p className="mt-1 text-sm text-muted">Choose your role to get the right access.</p>

      <div className="mt-6 space-y-3">
        {ROLES.map((r) => (
          <Link
            key={r.href}
            href={r.href}
            className="flex items-center gap-4 rounded-xl border border-navy-950/10 px-4 py-4 transition-colors hover:border-cyan/40 hover:bg-cyan/5"
          >
            <r.icon className="size-6 text-cyan" />
            <div>
              <div className="text-sm font-semibold">{r.label}</div>
              <div className="text-xs text-muted">{r.desc}</div>
            </div>
          </Link>
        ))}
      </div>

      <p className="mt-6 text-center text-sm text-muted">
        Already have an account?{" "}
        <Link href="/login" className="text-cyan hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
