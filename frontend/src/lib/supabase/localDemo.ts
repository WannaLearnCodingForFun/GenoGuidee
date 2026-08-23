/**
 * Offline / hackathon fallback used ONLY when Supabase env vars are absent.
 * Real auth, RLS, and role gating remain the current GitHub path when configured.
 */
type Chain = {
  select: (..._a: unknown[]) => Chain;
  eq: (..._a: unknown[]) => Chain;
  in: (..._a: unknown[]) => Chain;
  is: (..._a: unknown[]) => Chain;
  order: (..._a: unknown[]) => Chain;
  limit: (..._a: unknown[]) => Chain;
  single: () => Promise<{ data: null; error: null }>;
  then: Promise<{ data: unknown[]; error: null; count: number }>["then"];
};

function emptyQuery(): Chain {
  const resolved = Promise.resolve({ data: [] as unknown[], error: null, count: 0 });
  const chain = {} as Chain;
  chain.select = () => chain;
  chain.eq = () => chain;
  chain.in = () => chain;
  chain.is = () => chain;
  chain.order = () => chain;
  chain.limit = () => chain;
  chain.single = async () => ({ data: null, error: null });
  chain.then = resolved.then.bind(resolved);
  return chain;
}

const notConfigured = { message: "Identity provider not configured. Use the local demo workspace." };

export function createLocalDemoBrowserClient() {
  return {
    auth: {
      getSession: async () => ({ data: { session: null }, error: null }),
      getUser: async () => ({ data: { user: null }, error: null }),
      signInWithPassword: async () => ({
        data: { session: null, user: null },
        error: notConfigured,
      }),
      signUp: async () => ({ data: { session: null, user: null }, error: notConfigured }),
      signOut: async () => ({ error: null }),
      exchangeCodeForSession: async () => ({ error: notConfigured }),
    },
    from: () => emptyQuery(),
    rpc: () => ({
      single: async () => ({ data: null, error: notConfigured }),
      then: Promise.resolve({ data: null, error: notConfigured }).then.bind(
        Promise.resolve({ data: null, error: notConfigured }),
      ),
    }),
  };
}

export type LocalDemoRole = "doctor" | "patient" | "lab_technician";

export const LOCAL_DEMO_ACCOUNT = {
  id: "LOCAL-DEMO",
  name: "Local demo (synthetic)",
  role: "doctor" as LocalDemoRole,
  email: "demo@localhost",
};

const STORAGE_KEY = "genoguide_local_demo_account";

export function readLocalDemoAccount(): typeof LOCAL_DEMO_ACCOUNT {
  if (typeof window === "undefined") return LOCAL_DEMO_ACCOUNT;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return LOCAL_DEMO_ACCOUNT;
    const parsed = JSON.parse(raw) as Partial<typeof LOCAL_DEMO_ACCOUNT>;
    const role = parsed.role;
    if (role !== "doctor" && role !== "patient" && role !== "lab_technician") {
      return LOCAL_DEMO_ACCOUNT;
    }
    return {
      id: parsed.id || "LOCAL-DEMO",
      name: parsed.name || LOCAL_DEMO_ACCOUNT.name,
      role,
      email: parsed.email || LOCAL_DEMO_ACCOUNT.email,
    };
  } catch {
    return LOCAL_DEMO_ACCOUNT;
  }
}

export function writeLocalDemoAccount(account: {
  name: string;
  role: LocalDemoRole;
  email?: string;
}): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      id: "LOCAL-DEMO",
      name: account.name.trim() || LOCAL_DEMO_ACCOUNT.name,
      role: account.role,
      email: account.email?.trim() || LOCAL_DEMO_ACCOUNT.email,
    }),
  );
}

export function clearLocalDemoAccount(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(STORAGE_KEY);
}
