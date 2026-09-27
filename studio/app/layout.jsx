import './globals.css'

export const metadata = {
  title: 'AgentForge Studio',
  description: 'Local AI app builder',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en" data-theme="dark" className="dark" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link rel="stylesheet"
              href="https://fonts.googleapis.com/css2?family=Barlow:wght@600;700;800&family=DM+Sans:wght@400;500;600;700&family=Public+Sans:wght@400;500;600;700;800&display=swap" />
      </head>
      <body>{children}</body>
    </html>
  )
}
