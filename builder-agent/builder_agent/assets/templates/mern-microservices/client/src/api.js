/**
 * One place that knows how to talk to the gateway.
 *
 * Relative URLs only: the gateway serves this bundle from its own origin, so
 * an absolute localhost URL would work in development and break everywhere
 * else. The session cookie rides along because same-origin requests send it.
 */
export async function request(path, { method = 'GET', body, signal } = {}) {
  const response = await fetch('/api' + path, {
    method,
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  const text = await response.text();
  // A gateway that cannot reach a service answers 503 with JSON; a crashed one
  // can answer HTML. Parsing defensively keeps the real status in the error.
  let payload = null;
  try { payload = text ? JSON.parse(text) : null; } catch { payload = null; }
  if (!response.ok) {
    const error = new Error(payload?.error ?? ('Request failed (' + response.status + ')'));
    error.status = response.status;
    throw error;
  }
  return payload;
}

/** Money is stored in the smallest unit and formatted in exactly one place. */
export function formatPrice(cents) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format((cents ?? 0) / 100);
}
