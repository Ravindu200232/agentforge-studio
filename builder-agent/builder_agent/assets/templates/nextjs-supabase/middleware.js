import { createServerClient } from '@supabase/ssr';
import { NextResponse } from 'next/server';

/**
 * Supabase Auth's session is a short-lived access token behind a refresh token in the cookie. A
 * Server Component cannot write a cookie, so nothing renews that token unless something upstream
 * does it on every request - this is that something. Skipped for static assets, where there is no
 * session to refresh and doing so would cost a network round trip per file.
 */
export async function middleware(request) {
  let response = NextResponse.next({ request });
  const supabase = createServerClient(process.env.NEXT_PUBLIC_SUPABASE_URL, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (toSet) => {
        for (const { name, value } of toSet) request.cookies.set(name, value);
        response = NextResponse.next({ request });
        for (const { name, value, options } of toSet) response.cookies.set(name, value, options);
      },
    },
  });
  await supabase.auth.getUser();
  return response;
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)'],
};
