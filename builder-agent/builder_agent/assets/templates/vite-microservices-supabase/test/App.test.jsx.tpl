import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { App } from '../src/App.jsx';

/**
 * Replace these with the application's own component tests.
 *
 * They are here so `npm test` is green on the first run: a scaffold whose test
 * command fails teaches nothing about the code that was just written.
 */
describe('App', () => {
  it('renders its heading', () => {
    render(<App />);
    // Role and accessible name, the way a user and a screen reader find it.
    expect(screen.getByRole('heading', { name: 'Application' })).toBeInTheDocument();
  });
});
