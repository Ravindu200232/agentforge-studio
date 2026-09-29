import { createServerClient, parseCookieHeader, serializeCookieHeader } from '@supabase/ssr';
import { createClient } from '@supabase/supabase-js';

/**
 * One client per request, built from that request's own cookie header.
 *
 * Remix has no ambient `cookies()` the way Next's Server Components do: every `loader`/`action`
 * builds its own client from the request in flight, and must copy `headers` onto whatever it
 * returns, or a refreshed session is silently dropped.
 *
 *   export async function loader({ request }) {
 *     const headers = new Headers();
 *     const supabase = supabaseServer(request, headers);
 *     const { data: { user } } = await supabase.auth.getUser();
 *     return json({ user }, { headers });
 *   }
 */
export function supabaseServer(request, headers) {
  return createServerClient(process.env.SUPABASE_URL, process.env.SUPABASE_ANON_KEY, {
    cookies: {
      getAll: () => parseCookieHeader(request.headers.get('Cookie') ?? ''),
      setAll: (toSet) => {
        for (const { name, value, options } of toSet) {
          headers.append('Set-Cookie', serializeCookieHeader(name, value, options));
        }
      },
    },
  });
}

/** For a Client Component: given the `ENV` a loader passed down (see app/root.jsx), one browser client. */
export function supabaseBrowser(env) {
  return createClient(env.SUPABASE_URL, env.SUPABASE_ANON_KEY);
}

/**
 * The service-role key, RLS bypassed entirely. Only from a `loader`/`action` (server code), never
 * from anything a browser bundle could include, and never given the client's `ENV` treatment.
 */
export function supabaseAdmin() {
  return createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
}
