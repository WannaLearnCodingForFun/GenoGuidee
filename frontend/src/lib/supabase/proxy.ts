import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { allowedPathsForRole } from "@/lib/nav";
import type { Role } from "@/lib/useAccount";

const PROTECTED_PREFIXES = [
  "/dashboard",
  "/upload",
  "/clinical-workup",
  "/variant-lab",
  "/patient-context",
  "/knowledge-graph",
  "/provenance",
  "/therapy",
];

export async function updateSession(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  // Never remove — required to refresh the session token before it expires.
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const path = request.nextUrl.pathname;
  const isProtected = PROTECTED_PREFIXES.some((p) => path === p || path.startsWith(`${p}/`));

  if (isProtected && !user) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", path);
    return NextResponse.redirect(url);
  }

  // Phase B2 — server-side route guard. Client-side nav filtering alone is
  // not access control: a patient hitting /therapy directly must be blocked
  // here too. `role` is looked up from `profiles` (never client-asserted).
  if (isProtected && user) {
    const { data: profile } = await supabase
      .from("profiles")
      .select("role")
      .eq("id", user.id)
      .single();
    const role = (profile?.role ?? "") as Role;
    const allowed = allowedPathsForRole(role);
    const pathAllowed = allowed.some((p) => path === p || path.startsWith(`${p}/`));
    if (!pathAllowed) {
      const url = request.nextUrl.clone();
      url.pathname = "/dashboard";
      return NextResponse.redirect(url);
    }
  }

  return response;
}
