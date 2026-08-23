/** True only when the current GitHub frontend has a real Supabase project configured. */
export function isSupabaseConfigured(): boolean {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";
  return Boolean(url.startsWith("http") && key.length > 20);
}
