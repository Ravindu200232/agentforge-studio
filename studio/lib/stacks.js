/**
 * The application shapes a build can take.
 *
 * These mirror `builder_agent/scaffold.py`'s STACK_GUIDES: fixed contracts, chosen once and
 * never migrated away from mid-build. "Auto" (no choice) starts as DEFAULT_STACK.
 *
 * `needs` is which account connections a build of that stack uses: Supabase on every stack
 * (sign-in, uploads and Google login run on it), MongoDB too on the MongoDB stacks.
 */
export const STACKS = [
  {
    id: 'nextjs-supabase',
    name: 'Next.js + Supabase',
    blurb: 'One Next.js app on Postgres, with Supabase Auth, Storage and RLS. The usual choice.',
    needs: ['supabase'],
  },
  {
    id: 'nextjs-mongo',
    name: 'Next.js + MongoDB',
    blurb: 'One Next.js app on MongoDB, with session-based auth and a real Atlas database.',
    needs: ['supabase', 'mongodb'],
  },
  {
    id: 'vite-supabase',
    name: 'Vite + Supabase',
    blurb: 'A Vite + React SPA talking to Postgres directly through Supabase, RLS instead of a server.',
    needs: ['supabase'],
  },
  {
    id: 'vite-mongo',
    name: 'Vite + MongoDB',
    blurb: 'A Vite + React SPA with its own Express + MongoDB API server behind it.',
    needs: ['supabase', 'mongodb'],
  },
  {
    id: 'remix-supabase',
    name: 'Remix + Supabase',
    blurb: 'Remix v2 on Vite, on Postgres. Data in loaders and actions, rendered on the server.',
    needs: ['supabase'],
  },
  {
    id: 'mern-microservices',
    name: 'MERN microservices',
    blurb: 'A Vite React client behind an API gateway, independent MongoDB-backed services behind that.',
    needs: ['supabase', 'mongodb'],
  },
]

export const DEFAULT_STACK = 'nextjs-supabase'

/** The connections a build of `id` needs; Auto (empty) counts as DEFAULT_STACK. */
export const stackNeeds = (id) =>
  (STACKS.find(stack => stack.id === (id || DEFAULT_STACK)) || STACKS[0]).needs
