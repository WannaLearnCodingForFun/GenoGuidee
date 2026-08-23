import { createBrowserClient } from "@supabase/ssr";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { createLocalDemoBrowserClient } from "@/lib/supabase/localDemo";

type BrowserSupabase = ReturnType<typeof createBrowserClient>;

export function createClient(): BrowserSupabase {
  if (!isSupabaseConfigured()) {
    return createLocalDemoBrowserClient() as unknown as BrowserSupabase;
  }
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
