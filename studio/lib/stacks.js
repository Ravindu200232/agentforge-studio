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
    id: 'nextjs-mongo',
    name: 'Next.js + MongoDB',
    blurb: 'One Next.js app with route handlers and Mongoose. The usual choice.',
  },
  {
    id: 'mern-microservices',
    name: 'MERN microservices',
    blurb: 'React, Express services behind one gateway, a database per service.',
  },
  {
    id: 'remix-mongo',
    name: 'Remix + MongoDB',
    blurb: 'Remix v2 on Vite. Data in loaders and actions, rendered on the server.',
  },
]

export const stackName = (id) =>
  STACKS.find(stack => stack.id === id)?.name || 'read from the brief'
