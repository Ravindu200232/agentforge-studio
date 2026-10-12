/**
 * The application shapes a build can take.
 *
 * These mirror `builder_agent/scaffold.py`'s STACK_GUIDES: fixed contracts, chosen once and
 * never migrated away from mid-build. "Auto" (no choice) starts as DEFAULT_STACK.
 *
 * `needs` is which account connections a build of that stack uses. Supabase on the Supabase-database
 * stacks (sign-in, uploads and Google login run on it) and on the MongoDB stacks that keep uploaded
 * files in a Supabase Storage bucket; MongoDB on every MongoDB stack. A `-only` stack runs on
 * MongoDB alone: no Supabase login, and uploaded files are kept in MongoDB itself.
 */
export const STACKS = [
  {
    id: 'nextjs-supabase',
    name: 'Next.js + Supabase',
    blurb: 'One Next.js app on Postgres, with Supabase Auth, Storage and RLS. The usual choice.',
    needs: ['supabase'],
  },
  {
    id: 'vite-supabase',
    name: 'Vite + Supabase',
    blurb: 'A Vite + React SPA talking to Postgres directly through Supabase, RLS instead of a server.',
    needs: ['supabase'],
  },
  {
    id: 'remix-supabase',
    name: 'Remix + Supabase',
    blurb: 'Remix v2 on Vite, on Postgres. Data in loaders and actions, rendered on the server.',
    needs: ['supabase'],
  },
  {
    id: 'nextjs-mongo',
    name: 'Next.js + MongoDB + Supabase bucket',
    blurb: 'One Next.js app on MongoDB with session auth. Uploaded files go in a Supabase Storage bucket.',
    needs: ['supabase', 'mongodb'],
  },
  {
    id: 'vite-mongo',
    name: 'Vite + MongoDB + Supabase bucket',
    blurb: 'A Vite + React SPA with its own Express + MongoDB API server. Uploaded files go in a Supabase Storage bucket.',
    needs: ['supabase', 'mongodb'],
  },
  {
    id: 'remix-mongo',
    name: 'Remix + MongoDB + Supabase bucket',
    blurb: 'Remix v2 on Vite with MongoDB and session auth. Uploaded files go in a Supabase Storage bucket.',
    needs: ['supabase', 'mongodb'],
  },
  {
    id: 'mern-microservices',
    name: 'MERN + Supabase bucket',
    blurb: 'A Vite React client behind an API gateway, independent MongoDB-backed services behind that. Uploaded files go in a Supabase Storage bucket.',
    needs: ['supabase', 'mongodb'],
  },
  {
    id: 'nextjs-mongo-only',
    name: 'Next.js + MongoDB',
    blurb: 'One Next.js app on MongoDB with session auth. MongoDB is the only account it needs; uploaded files are kept in MongoDB.',
    needs: ['mongodb'],
  },
  {
    id: 'vite-mongo-only',
    name: 'Vite + MongoDB',
    blurb: 'A Vite + React SPA with its own Express + MongoDB API server. MongoDB is the only account it needs.',
    needs: ['mongodb'],
  },
  {
    id: 'remix-mongo-only',
    name: 'Remix + MongoDB',
    blurb: 'Remix v2 on Vite with MongoDB and session auth. MongoDB is the only account it needs; uploaded files are kept in MongoDB.',
    needs: ['mongodb'],
  },
  {
    id: 'mern-microservices-only',
    name: 'MERN',
    blurb: 'A Vite React client behind an API gateway, independent MongoDB-backed services behind that. MongoDB is the only account it needs.',
    needs: ['mongodb'],
  },
]

export const DEFAULT_STACK = 'nextjs-supabase'

/** The connections a build of `id` needs; Auto (empty) counts as DEFAULT_STACK. */
export const stackNeeds = (id) =>
  (STACKS.find(stack => stack.id === (id || DEFAULT_STACK)) || STACKS[0]).needs
