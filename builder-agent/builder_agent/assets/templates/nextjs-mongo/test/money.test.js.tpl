import { describe, it, expect } from 'vitest';
import { formatPrice, lineTotal } from '@/lib/money.js';

describe('formatPrice', () => {
  it('formats cents as the string the page will really contain', () => {
    expect(formatPrice(4500)).toBe('$45.00');
    expect(formatPrice(850)).toBe('$8.50');
  });

  it('treats a missing price as zero rather than throwing', () => {
    expect(formatPrice(undefined)).toBe('$0.00');
  });
});

describe('lineTotal', () => {
  it('computes the total the cart renders', () => {
    expect(formatPrice(lineTotal(2250, 2))).toBe('$45.00');
  });
});
