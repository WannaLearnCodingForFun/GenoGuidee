import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { createLocalDemoBrowserClient } from "@/lib/supabase/localDemo";

export async function createClient() {
  if (!isSupabaseConfigured()) {
    return createLocalDemoBrowserClient() as unknown as ReturnType<typeof createServerClient>;
  }

  const cookieStore = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options),
            );
          } catch {
            // setAll called from a Server Component — safe to ignore when
            // middleware is also refreshing the session.
          }
        },
      },
    },
  );
}
