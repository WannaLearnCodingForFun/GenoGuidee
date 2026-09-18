const KEY = "genoguide_platform_session";

export interface PlatformSession {
  variantId?: string;
  interpretationId?: string;
  patientId?: number;
  caseId?: string;
}

export function readPlatformSession(): PlatformSession {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as PlatformSession;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

export function writePlatformSession(patch: PlatformSession): PlatformSession {
  const next = { ...readPlatformSession(), ...patch };
  if (typeof window !== "undefined") {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  }
  return next;
}

const IDS_KEY = "genoguide_interpretation_ids";

export function rememberedInterpretationIds(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(IDS_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export function rememberInterpretationId(id: string): void {
  if (!id) return;
  const next = [id, ...rememberedInterpretationIds().filter((x) => x !== id)].slice(0, 40);
  window.localStorage.setItem(IDS_KEY, JSON.stringify(next));
  writePlatformSession({ interpretationId: id });
}
