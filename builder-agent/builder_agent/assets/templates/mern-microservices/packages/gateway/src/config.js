/**
 * The gateway owns the only public port. Every service address is internal and
 * discovered from configuration, never hardcoded at a call site.
 */
export function loadConfig(env = process.env) {
  return {
    port: Number(env.PORT ?? 4000),
    services: {
      catalog: env.CATALOG_URL ?? `http://127.0.0.1:${env.CATALOG_PORT ?? 4001}`,
    },
  };
}
