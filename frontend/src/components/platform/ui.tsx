import type { ComponentType, ReactNode } from "react";
import { classColor, levelColor } from "@/lib/ui";

export function pageWrap(children: ReactNode) {
  return <div className="mx-auto max-w-7xl px-6 py-10 sm:px-8">{children}</div>;
}

export function PageHeader({
  icon: Icon,
  title,
  subtitle,
  actions,
}: {
  icon?: ComponentType<{ className?: string }>;
  title: string;
  subtitle: string;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="flex items-center gap-3 text-2xl font-bold tracking-tight">
          {Icon ? <Icon className="size-6 text-cyan" /> : null}
          {title}
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">{subtitle}</p>
      </div>
      {actions}
    </header>
  );
}

export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p className="mb-4 rounded-lg border border-error/30 bg-error/5 px-3 py-2 text-sm text-error">{message}</p>
  );
}

export function EmptyState({ text }: { text: string }) {
  return <p className="rounded-lg border border-dashed border-navy-950/10 p-4 text-sm text-muted">{text}</p>;
}

export function SkeletonCard() {
  return <div className="card h-24 animate-pulse bg-panel2/60" />;
}

export function SkeletonRows({ n = 5 }: { n?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="h-10 animate-pulse rounded-lg bg-panel2/70" />
      ))}
    </div>
  );
}

export function primaryBtn(disabled?: boolean) {
  return `rounded-lg border border-cyan/50 bg-cyan/10 px-4 py-2 text-sm font-semibold text-cyan transition-all hover:bg-cyan/15 disabled:opacity-50 ${disabled ? "opacity-50" : ""}`;
}

export function ghostBtn() {
  return "rounded-lg border border-navy-950/10 px-4 py-2 text-sm font-semibold text-muted transition-all hover:border-navy-950/25 hover:text-fg";
}

export function StatusBadge({ label }: { label: string }) {
  const up = label.replace(/_/g, " ");
  const cls = classColor(
    up.toLowerCase().includes("likely pathogenic")
      ? "Likely Pathogenic"
      : up.toLowerCase().includes("likely benign")
        ? "Likely Benign"
        : up.toLowerCase().includes("pathogenic")
          ? "Pathogenic"
          : up.toLowerCase().includes("benign")
            ? "Benign"
            : up.toLowerCase().includes("vus")
              ? "VUS"
              : "",
  );
  const extra =
    /CONFLICT|HIGH|REJECT|ERROR/i.test(label)
      ? "text-error border-error/40 bg-error/10"
      : /MIXED|MODERATE|REVIEW|PENDING|UNCERTAIN|UNKNOWN/i.test(label)
        ? "text-warning border-warning/40 bg-warning/10"
        : /CONCORDANT|FINAL|ACCEPT|SUPPORT|LOW\b|IN-DISTRIBUTION|IN_DISTRIBUTION/i.test(label)
          ? "text-success border-success/40 bg-success/10"
          : /INSUFFICIENT|MISSING|AI_DRAFT|SIMULATION/i.test(label)
            ? "text-muted border-navy-950/15 bg-panel2"
            : `${cls.text} ${cls.bg} ${cls.border}`;
  return (
    <span className={`inline-flex rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${extra}`}>
      {up}
    </span>
  );
}

export function DriftBadge({ level }: { level: string }) {
  return (
    <span className={`inline-flex rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${levelColor(level)}`}>
      {level}
    </span>
  );
}

export function fieldClass() {
  return "w-full rounded-lg border border-navy-950/10 bg-white px-3 py-2 text-sm outline-none focus:border-cyan/40";
}
