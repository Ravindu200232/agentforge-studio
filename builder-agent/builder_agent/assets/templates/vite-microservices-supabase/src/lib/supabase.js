import { createClient } from '@supabase/supabase-js';

/**
 * The one Supabase client this app has - there is no server, so there is no separate
 * server/browser split the way the Next.js and Remix stacks need. Every environment variable
 * here is public (Vite compiles `VITE_*` into the bundle), so `SUPABASE_SERVICE_ROLE_KEY` must
 * never be referenced anywhere in this project: this client only ever carries the anon key, and
 * Row Level Security is what decides what it may read or write.
 */
export const supabase = createClient(import.meta.env.VITE_SUPABASE_URL, import.meta.env.VITE_SUPABASE_ANON_KEY);
