import type { NavItem } from "@/lib/nav";
import { platformFlag, platformNavEnabled, PLATFORM_FLAGS } from "@/lib/platformFlags";
import type { Role } from "@/lib/useAccount";

export type NavGroup = "core" | "knowledge" | "platform";

export interface GroupedNavItem extends NavItem {
  group: NavGroup;
}

const PLATFORM_ALL: GroupedNavItem[] = [
  { href: "/evidence-intelligence", label: "Evidence Intelligence", group: "platform" },
  { href: "/reanalysis", label: "Reanalysis", group: "platform" },
  { href: "/curation", label: "Curation", group: "platform" },
  { href: "/phenotype-analysis", label: "Phenotype Analysis", group: "platform" },
  { href: "/inheritance", label: "Inheritance", group: "platform" },
  { href: "/acmg-simulator", label: "ACMG Simulator", group: "platform" },
  { href: "/phenopackets", label: "Phenopackets", group: "platform" },
  { href: "/model-monitoring", label: "Model Monitoring", group: "platform" },
];

function flagForHref(href: string): boolean {
  if (href === "/reanalysis") return PLATFORM_FLAGS.reanalysis();
  if (href === "/curation") return PLATFORM_FLAGS.curation();
  if (href === "/acmg-simulator") return PLATFORM_FLAGS.acmgSimulator();
  if (href === "/phenopackets") return PLATFORM_FLAGS.phenopackets();
  if (href === "/model-monitoring") return PLATFORM_FLAGS.modelMonitoring();
  if (href === "/evidence-intelligence") return platformFlag("NEXT_PUBLIC_ENABLE_EVIDENCE_INTELLIGENCE", true);
  if (href === "/phenotype-analysis") return platformFlag("NEXT_PUBLIC_ENABLE_PHENOTYPE_ANALYSIS", true);
  if (href === "/inheritance") return platformFlag("NEXT_PUBLIC_ENABLE_INHERITANCE", true);
  return true;
}

export function platformNavForRole(role: Role): GroupedNavItem[] {
  if (!platformNavEnabled()) return [];
  if (role !== "doctor" && role !== "lab_technician") return [];
  return PLATFORM_ALL.filter((item) => flagForHref(item.href));
}

export const NAV_GROUP_ORDER: NavGroup[] = ["core", "knowledge", "platform"];

export const NAV_GROUP_LABEL: Record<NavGroup, string> = {
  core: "Core",
  knowledge: "Knowledge",
  platform: "Platform",
};

export function groupForHref(href: string): NavGroup {
  if (
    href === "/knowledge-graph" ||
    href === "/provenance" ||
    href === "/model-evaluation"
  ) {
    return "knowledge";
  }
  if (PLATFORM_ALL.some((p) => p.href === href) || href.startsWith("/interpretations")) {
    return "platform";
  }
  return "core";
}
