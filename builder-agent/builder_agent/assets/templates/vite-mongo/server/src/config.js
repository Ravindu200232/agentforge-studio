/**
 * The server owns the only public port. A value that changes how it runs comes from
 * the environment, never a hardcoded local address.
 */
export function loadConfig(env = process.env) {
  return {
    port: Number(env.PORT ?? 4100),
    mongodbUri: env.MONGODB_URI ?? 'mongodb://127.0.0.1:27017/__APP_DB__',
  };
}
