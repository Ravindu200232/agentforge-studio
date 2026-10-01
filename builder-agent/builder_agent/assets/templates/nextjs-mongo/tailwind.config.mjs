/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class', '[data-theme="dark"]'],
  content: [
    './app/**/*.{js,jsx}',
    './components/**/*.{js,jsx}',
    './lib/**/*.{js,jsx}',
  ],
  theme: {
    // The design contract writes these custom properties; reading them here is
    // what makes a Tailwind class and a token the same decision.
    extend: {
      colors: {
        background: 'var(--background)', foreground: 'var(--text)',
        surface: 'var(--surface)', border: 'var(--border)',
        muted: 'var(--muted)', primary: 'var(--primary)',
        'primary-foreground': 'var(--on-primary)', accent: 'var(--accent)',
      },
      borderRadius: { DEFAULT: 'var(--radius)', xl: 'var(--radius)' },
      fontFamily: { sans: ['var(--font-body)'], display: ['var(--font-heading)'] },
    },
  },
  plugins: [],
};
