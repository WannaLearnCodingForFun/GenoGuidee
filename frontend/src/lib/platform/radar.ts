import type { AnalyzeResult } from "@/lib/api";
import type { EvidenceCategory, RadarItem } from "@/lib/platform/types";

export function radarBodyFromAnalyze(result: AnalyzeResult): Record<string, unknown> {
  const v = result.variant;
  return {
    clinvar: null,
    clingen: null,
    gnomad: v.gnomad_af,
    alphamissense: null,
    revel: v.revel,
    spliceai: v.spliceai,
    cadd: v.cadd,
    functional: null,
    literature: null,
    acmg: result.acmg.classification,
    ml: result.ml.top_class,
    phenotype: null,
  };
}

export function evidenceFilter(category: string): "Supporting" | "Contradicting" | "Uncertain" | "Missing" {
  if (category === "PATHOGENIC_SUPPORT") return "Supporting";
  if (category === "BENIGN_SUPPORT") return "Contradicting";
  if (category === "MISSING") return "Missing";
  return "Uncertain";
}

export function categoryLabel(category: EvidenceCategory | string): string {
  return evidenceFilter(category).toUpperCase();
}

export function itemDetailText(item: RadarItem): string {
  const d = item.detail;
  if (d == null || d === false) return "Not available";
  if (typeof d === "string" || typeof d === "number" || typeof d === "boolean") return String(d);
  try {
    return JSON.stringify(d);
  } catch {
    return "See source";
  }
}
