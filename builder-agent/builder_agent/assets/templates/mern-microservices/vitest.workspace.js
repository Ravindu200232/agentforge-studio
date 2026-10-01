/**
 * One command that runs every workspace's suite with that workspace's own
 * config.
 *
 * Without this, a bare `vitest run` at the repository root uses no config at
 * all: the client's tests execute without jsdom and without the React plugin,
 * and fail with errors that have nothing to do with the code. `npm test` was
 * always correct; this makes the shorter command correct too.
 */
export default ['packages/*', 'client'];
