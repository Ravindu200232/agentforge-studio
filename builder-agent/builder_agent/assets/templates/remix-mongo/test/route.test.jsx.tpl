import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import HomeRoute from '~/routes/_index.jsx';

/**
 * A route's component is an ordinary React component, so it is tested as one.
 *
 * What it must NOT be tested through is `createRemixStub` for a page that has
 * no loader — that spins up a router for nothing. Reach for the stub when the
 * component actually uses `useLoaderData`, `Link` or `Form`; render it
 * directly when it does not.
 */
describe('the home route', () => {
  it('renders a heading the page can be found by', () => {
    render(<HomeRoute />);
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument();
  });
});
