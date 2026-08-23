export function classColor(cls: string): { text: string; bg: string; border: string } {
  switch (cls) {
    case "Pathogenic":
      return { text: "text-error", bg: "bg-error/10", border: "border-error/40" };
    case "Likely Pathogenic":
      return { text: "text-warning", bg: "bg-warning/10", border: "border-warning/40" };
    case "VUS":
      return { text: "text-violet", bg: "bg-violet/10", border: "border-violet/40" };
    case "Likely Benign":
      return { text: "text-cyan", bg: "bg-cyan/10", border: "border-cyan/30" };
    case "Benign":
      return { text: "text-success", bg: "bg-success/10", border: "border-success/40" };
    default:
      return { text: "text-muted", bg: "bg-white/5", border: "border-white/10" };
  }
}

export function levelColor(level: string): string {
  if (level === "HIGH") return "text-error border-error/40 bg-error/10";
  if (level === "MODERATE") return "text-warning border-warning/40 bg-warning/10";
  return "text-success border-success/40 bg-success/10";
}

export function shortHash(h: string, n = 10): string {
  if (!h) return "";
  return `${h.slice(0, n)}…${h.slice(-6)}`;
}

export function formatAf(af: number | null | undefined): string {
  if (af == null || Number.isNaN(af)) return "—";
  if (af === 0) return "Absent";
  if (af < 0.0001) return af.toExponential(1);
  return af.toFixed(4);
}

export function timestampLabel(ts: number): string {
  return new Date(ts * 1000).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
