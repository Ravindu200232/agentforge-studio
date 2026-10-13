# AgentForge 1.1.0 for macOS (Apple Silicon)

Download the DMG and drag AgentForge to Applications.

This build includes the latest AgentForge Studio changes:

- Supabase sign-in through the official CLI, including browser verification codes and accounts without organizations.
- Reliable Supabase OAuth callbacks when the usual local port is busy.
- Supabase database previews and table samples using the project's database connection.
- Formatted Supabase tables, migrations, statistics, and settings instead of printed JSON.
- API key and edge-function secret values hidden from both formatted and Raw preview views.
- The Design Select sample website preview fix.

The app bundles Python 3.12, Node.js 24, the privacy runtime, and Playwright Chromium. Supabase integration also requires the official CLI: brew install supabase/tap/supabase.

The app is ad-hoc signed but not Apple-notarized. If macOS blocks the first launch, Control-click AgentForge and choose Open.
