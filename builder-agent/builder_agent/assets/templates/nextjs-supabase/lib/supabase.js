import { createBrowserClient, createServerClient } from '@supabase/ssr';
import { createClient } from '@supabase/supabase-js';
import { cookies } from 'next/headers';

/**
 * Three clients, three trust levels — never mix them up.
 *
 * `supabaseServer()` is per-request: it reads and writes the session cookie through the request in
 * flight, so it must be built fresh inside a Server Component, a Route Handler or an action, never
 * cached at module scope. It carries the signed-in user's own session, so every query it makes is
 * still subject to Row Level Security.
 *
 * `supabaseBrowser()` is one client for the whole page, built once on the client, for anything a
 * Client Component queries directly with the anon key (also RLS-gated).
 *
 * `supabaseAdmin()` uses the service-role key and bypasses RLS entirely. It exists for exactly the
 * operations a policy cannot express (an admin action, a seed script, an Edge-Function-style job) —
 * never import it into a Client Component, and never let its key carry the `NEXT_PUBLIC_` prefix.
 */
export async function supabaseServer() {
  const cookieStore = await cookies();
  return createServerClient(process.env.NEXT_PUBLIC_SUPABASE_URL, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY, {
    cookies: {
      getAll: () => cookieStore.getAll(),
      setAll: (toSet) => {
        try {
          for (const { name, value, options } of toSet) cookieStore.set(name, value, options);
        } catch {
          // Called from a Server Component that cannot set cookies - middleware.js refreshes the
          // session on every request instead, so this is safe to ignore here.
        }
      },
    },
  });
}

export function supabaseBrowser() {
  return createBrowserClient(process.env.NEXT_PUBLIC_SUPABASE_URL, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY);
}

export function supabaseAdmin() {
  return createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
}
