// One service, one function. Copy this folder to `supabase/functions/<service-name>/` for each
// bounded context the specification calls out as its own service - see
// `_guides/nextjs-microservices-supabase.md` for when a function is the right tool versus a plain
// RLS-gated table read. Deploy with `supabase functions deploy <service-name>`; call from the
// frontend with `supabase.functions.invoke('<service-name>', { body: {...} })`, never a hand-rolled
// internal URL - there is no gateway and no internal port scheme, Supabase's own platform routes it.
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

Deno.serve(async (request) => {
  // Every function sets its own CORS headers - Supabase adds none automatically, and a missing
  // header fails silently in the browser with nothing server-side to point at.
  const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'authorization, content-type' };
  if (request.method === 'OPTIONS') return new Response(null, { headers: cors });

  // The service-role key is this function's own secret (`supabase secrets set`), never one baked
  // into the frontend bundle - this is the one thing a plain RLS-gated table read cannot do safely.
  const admin = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!);
  const body = await request.json().catch(() => ({}));

  return new Response(JSON.stringify({ ok: true, received: body }), {
    headers: { ...cors, 'Content-Type': 'application/json' },
  });
});
