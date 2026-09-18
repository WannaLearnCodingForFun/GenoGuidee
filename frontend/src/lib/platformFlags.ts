/** Frontend flags. Legacy routes ignore these. Default on. */
export function platformNavEnabled(): boolean {
  const raw = process.env.NEXT_PUBLIC_ENABLE_PLATFORM_FEATURES;
  if (raw == null || raw === "") return true;
  return raw.toLowerCase() === "true" || raw === "1";
}

export function platformFlag(name: string, fallback = true): boolean {
  if (!platformNavEnabled()) return false;
  const raw = process.env[name];
  if (raw == null || raw === "") return fallback;
  return raw.toLowerCase() === "true" || raw === "1";
}

export const PLATFORM_FLAGS = {
  reanalysis: () => platformFlag("NEXT_PUBLIC_ENABLE_REANALYSIS"),
  curation: () => platformFlag("NEXT_PUBLIC_ENABLE_CURATION"),
  acmgSimulator: () => platformFlag("NEXT_PUBLIC_ENABLE_ACMG_SIMULATOR"),
  phenopackets: () => platformFlag("NEXT_PUBLIC_ENABLE_PHENOPACKETS"),
  modelMonitoring: () => platformFlag("NEXT_PUBLIC_ENABLE_MODEL_MONITORING"),
};
