/**
 * Money is stored in cents and formatted in exactly one place.
 *
 * Two formatters drift, and the difference shows up as a failing E2E assertion
 * on a string nobody can find in the source.
 */
export function formatPrice(cents) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format((cents ?? 0) / 100);
}

/** A line total is computed, never rendered as "2 x $22.50". */
export function lineTotal(cents, quantity) {
  return (cents ?? 0) * (quantity ?? 0);
}
