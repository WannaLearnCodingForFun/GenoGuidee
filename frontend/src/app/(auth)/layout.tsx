import Link from "next/link";
import { Dna } from "lucide-react";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-6 py-16">
      <div className="absolute inset-0 grid-texture" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_50%_0%,rgba(180,24,45,0.07),transparent_70%)]" />

      <div className="relative z-10 w-full max-w-md">
        <Link href="/" className="mb-8 flex items-center justify-center gap-3">
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
        {children}
      </div>
    </div>
  );
}
