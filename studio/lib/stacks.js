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
    id: 'nextjs-mongo',
    name: 'Next.js + MongoDB',
    blurb: 'One Next.js app on MongoDB, with session-based auth and a real Atlas database.',
  },
  {
    id: 'vite-supabase',
    name: 'Vite + Supabase',
    blurb: 'A Vite + React SPA talking to Postgres directly through Supabase, RLS instead of a server.',
  },
  {
    id: 'vite-mongo',
    name: 'Vite + MongoDB',
    blurb: 'A Vite + React SPA with its own Express + MongoDB API server behind it.',
  },
  {
    id: 'remix-supabase',
    name: 'Remix + Supabase',
    blurb: 'Remix v2 on Vite, on Postgres. Data in loaders and actions, rendered on the server.',
  },
  {
    id: 'mern-microservices',
    name: 'MERN microservices',
    blurb: 'A Vite React client behind an API gateway, independent MongoDB-backed services behind that.',
  },
]

export const stackName = (id) =>
  STACKS.find(stack => stack.id === id)?.name || 'read from the brief'
