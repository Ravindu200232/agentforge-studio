/**
 * The application shapes a build can take.
 *
 * These mirror `builder_agent/config.py`: fixed contracts, chosen once and
 * never migrated away from mid-build. The engine will read the stack out of
 * the brief when nothing is chosen here, which is what it always did — this
 * list exists so the choice can also be made on purpose.
 */
export const STACKS = [
  {
    id: 'nextjs-supabase',
    name: 'Next.js + Supabase',
    blurb: 'One Next.js app on Postgres, with Supabase Auth, Storage and RLS. The usual choice.',
  },
  {
    id: 'nextjs-microservices-supabase',
    name: 'Next.js + microservices + Supabase',
    blurb: 'Next.js frontend; independent Supabase Edge Functions behind it, one Postgres project.',
  },
  {
    id: 'vite-supabase',
    name: 'Vite + Supabase',
    blurb: 'A Vite + React SPA talking to Postgres directly through Supabase, RLS instead of a server.',
  },
  {
    id: 'vite-microservices-supabase',
    name: 'Vite + microservices + Supabase',
    blurb: 'Vite + React SPA; independent Supabase Edge Functions behind it, one Postgres project.',
  },
  {
    id: 'remix-supabase',
    name: 'Remix + Supabase',
    blurb: 'Remix v2 on Vite, on Postgres. Data in loaders and actions, rendered on the server.',
  },
]

export const stackName = (id) =>
  STACKS.find(stack => stack.id === id)?.name || 'read from the brief'
