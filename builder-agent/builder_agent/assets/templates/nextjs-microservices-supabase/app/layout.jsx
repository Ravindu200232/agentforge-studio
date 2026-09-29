import './globals.css';

export const metadata = {
  title: 'Application',
  description: 'Replace this metadata with the application\u2019s own.',
};

/**
 * The one place `globals.css` is imported. A stylesheet imported from a page
 * instead loads only on that route, and the app looks unstyled everywhere
 * else.
 */
export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
