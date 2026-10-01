import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import HomePage from '@/app/page.jsx';

/**
 * Replace this with the application's own page and component tests.
 *
 * It is here so `npm test` is green on the first run, and so the jsdom
 * environment, the `@` alias and the jest-dom matchers are all proven together
 * before any feature depends on them.
 */
describe('HomePage', () => {
  it('renders its heading', () => {
    render(<HomePage />);
    expect(screen.getByRole('heading', { name: 'Application' })).toBeInTheDocument();
  });
});
